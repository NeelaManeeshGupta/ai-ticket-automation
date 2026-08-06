import json
import logging
import re
from typing import Dict, Any
from config import settings
from schemas.ticket_schemas import ExtractionResult

logger = logging.getLogger(__name__)

class LLMExtractorService:
    """AI Extraction Service to extract structured SAP ticket fields from Email & OCR content."""

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.use_mock = settings.USE_MOCK_LLM or not bool(self.api_key.strip())

    def extract_incident_data(
        self,
        sender_name: str,
        sender_email: str,
        subject: str,
        email_body: str,
        ocr_text: str,
        image_parts: list = None
    ) -> ExtractionResult:
        """Extracts structured SAP incident data using Gemini API or heuristic mock parser."""

        if self.use_mock or not self.api_key:
            logger.info("LLM Extractor running in MOCK mode.")
            return self._heuristic_mock_extract(
                sender_name=sender_name,
                sender_email=sender_email,
                subject=subject,
                email_body=email_body,
                ocr_text=ocr_text
            )

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)

            prompt_text = f"""
You are an expert SAP Support Incident Classifier & Data Extractor.
Analyze the following customer email, OCR text, and attached image screenshots to determine if it is a valid SAP Support Incident and extract structured details.

CLASSIFICATION RULES:
- "is_sap_incident": true ONLY if the email describes a real SAP system error, transaction code issue (VA01, ME21N, FB01, ST22, etc.), ABAP dump, system configuration error, or enterprise IT support request.
- "is_sap_incident": false if the email is a developer news digest, marketing email, social platform notification (Reddit, daily.dev, GitHub update), personal message, or non-SAP communication.

FIELD EXTRACTION RULES:
- "customer_name": Extract the actual reporter's name from signature at the end of email (e.g. "Regards, David" -> "David"). If no signature name exists, use Sender Name.
- "company_name": Extract company/organization name mentioned in body or signature (e.g. "ABC Technologies Pvt Ltd").
- "component": Classify exact SAP Module/Service:
  - SAP Joule / BTP -> "BTP-JOULE"
  - Fiori / UI5 -> "FIORI"
  - Sales Order / VA01 -> "SD-BF"
  - Purchase Order / ME21N -> "MM-PUR"
  - Finance / FB01 -> "FI-CO"
  - Short Dump / ST22 / SM37 / SU53 / Basis -> "BASIS"
  - HANA Database -> "HANA-DB"
- "priority": Score based on impact:
  - If text mentions "multiple users affected", "business approvals delayed", "unable to execute", "PRD down", or "blocker" -> "2-High" or "1-Very High".
  - Otherwise -> "3-Medium".

INPUT DATA:
- Sender Name: {sender_name}
- Sender Email: {sender_email}
- Subject: {subject}
- Email Body:
{email_body}

- OCR Extracted Attachment Text:
{ocr_text}

OUTPUT FORMAT REQUIREMENTS:
Return ONLY valid raw JSON matching this JSON schema:
{{
  "is_sap_incident": true or false,
  "relevance_reason": "Brief justification for is_sap_incident classification",
  "customer_name": "Full name of reporter extracted from signature or email",
  "customer_email": "Reporter email address",
  "company_name": "Company/Organization name extracted from signature or email",
  "system_id": "SAP System ID (e.g. PRD, DEV, QAS, S4H)",
  "client": "SAP Client / Mandant (e.g. 100, 800, 200)",
  "component": "SAP Module (e.g. BTP-JOULE, SD-BF, MM-PUR, FI-CO, BASIS, FIORI)",
  "tcode": "SAP Transaction Code if mentioned (e.g. VA01, ME21N, ST22, SU53)",
  "category": "Incident category (e.g. Short Dump, Configuration Error, Authorization Issue, Cloud Service Outage)",
  "priority": "Severity (1-Very High, 2-High, 3-Medium, 4-Low)",
  "problem_description": "Comprehensive summary of problem description",
  "error_code": "SAP Error Code or Exception ID if present",
  "error_message": "Exact SAP Error message extracted",
  "attachment_details": "Brief summary of attachment findings"
}}
"""

            contents = [prompt_text]
            if image_parts:
                for img in image_parts:
                    contents.append(types.Part.from_bytes(
                        data=img['data'],
                        mime_type=img['mime_type']
                    ))

            candidate_models = ['gemini-2.0-flash', 'gemini-flash-latest', 'gemini-2.0-flash-lite']
            response_text = None

            for model_name in candidate_models:
                try:
                    logger.info(f"Attempting Gemini extraction with model '{model_name}'...")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )
                    if response and response.text:
                        response_text = response.text.strip()
                        logger.info(f"Gemini model '{model_name}' returned successful response.")
                        break
                except Exception as model_err:
                    logger.warning(f"Gemini model '{model_name}' failed: {model_err}. Trying next candidate...")

            if not response_text:
                raise RuntimeError("All Gemini candidate models failed to return a response.")

            data = json.loads(response_text)
            return ExtractionResult(**data)

        except Exception as e:
            logger.error(f"Gemini API extraction failed: {str(e)}. Falling back to mock extractor.")
            return self._heuristic_mock_extract(
                sender_name=sender_name,
                sender_email=sender_email,
                subject=subject,
                email_body=email_body,
                ocr_text=ocr_text
            )

    def _heuristic_mock_extract(
        self,
        sender_name: str,
        sender_email: str,
        subject: str,
        email_body: str,
        ocr_text: str
    ) -> ExtractionResult:
        """Heuristic mock parser for instant local testing without LLM API keys."""
        combined_text = f"{subject}\n{email_body}\n{ocr_text}"
        lower_text = combined_text.lower()

        # Dynamic Error Message Extraction
        error_msg = ""
        error_match = re.search(r"(?:error message|error code|error|reason|issue|exception):\s*([^\n\r.]+)", combined_text, re.IGNORECASE)
        if error_match:
            error_msg = error_match.group(1).strip()
        elif subject and len(subject.strip()) > 5:
            error_msg = subject.strip()
        elif email_body and len(email_body.strip()) > 5:
            error_msg = email_body.strip().split('\n')[0][:120]
        else:
            error_msg = "SAP System Support Issue Reported"

        # Dynamic Error Code Extraction
        error_code = None
        code_match = re.search(r"\b(ERR_[A-Z0-9_]+|CX_[A-Z0-9_]+|SAP_[A-Z0-9_]+)\b", combined_text)
        if code_match:
            error_code = code_match.group(1)

        # Extract System ID (e.g., PRD, DEV, QAS)
        system_id = "PRD"
        sys_match = re.search(r"\b(PRD|DEV|QAS|S4H|BW1)\b", combined_text, re.IGNORECASE)
        if sys_match:
            system_id = sys_match.group(1).upper()

        # Extract Client number
        client = "100"
        client_match = re.search(r"(?:client|mandant)\s*:?\s*(\d{3})", combined_text, re.IGNORECASE)
        if client_match:
            client = client_match.group(1)

        # Extract Transaction Code
        tcode = None
        tcode_match = re.search(r"\b(VA01|ME21N|FB01|ST22|SU53|SM37|SE16|SE80)\b", combined_text, re.IGNORECASE)
        if tcode_match:
            tcode = tcode_match.group(1).upper()

        # Component Detection
        component = "GENERAL"
        if "joule" in lower_text or "btp" in lower_text:
            component = "BTP-JOULE"
        elif "fiori" in lower_text or "ui5" in lower_text:
            component = "FIORI"
        elif tcode == "VA01" or "sales" in lower_text:
            component = "SD-BF"
        elif tcode == "ME21N" or "purchase" in lower_text:
            component = "MM-PUR"
        elif tcode == "FB01" or "finance" in lower_text:
            component = "FI-CO"
        elif "basis" in lower_text or tcode in ["ST22", "SM37", "SU53"]:
            component = "BASIS"

        # Priority Assessment
        priority = "3-Medium"
        if any(kw in lower_text for kw in ["multiple users", "approvals delayed", "delayed", "unable to execute", "urgent", "critical", "blocker", "system down"]):
            priority = "2-High"
        if "prd" in lower_text and any(kw in lower_text for kw in ["down", "blocker", "critical"]):
            priority = "1-Very High"

        # Extract Reporter Name & Company from Signature (e.g. Thanks, \n Michael \n XYZ Technologies)
        cust_name = sender_name
        company = ""

        sig_lines = re.split(r"(?:thanks|regards|sincerely|cheers)\s*,?", email_body, flags=re.IGNORECASE)
        if len(sig_lines) > 1:
            after_sig = sig_lines[-1].strip().split('\n')
            non_empty = [l.strip() for l in after_sig if l.strip()]
            if len(non_empty) >= 1 and len(non_empty[0].split()) <= 3:
                candidate_name = non_empty[0]
                if candidate_name.lower() not in ["customer", "support", "team"]:
                    cust_name = candidate_name
            if len(non_empty) >= 2 and len(non_empty[1].split()) <= 5:
                company = non_empty[1]

        if not company:
            comp_match = re.search(r"(?:customer|company|organization|from):?\s*([A-Za-z0-9\s]+(?:Pvt|Ltd|Inc|Corp|GmbH|Technologies|Solutions|Logistics|Systems|Services)[A-Za-z0-9\s]*)", email_body, re.IGNORECASE)
            if comp_match:
                raw_comp = comp_match.group(1).strip()
                company = re.split(r"\b(regards|thanks|sincerely|customer)\b", raw_comp, flags=re.IGNORECASE)[0].strip()
            else:
                comp_match2 = re.search(r"(?:inc|corp|ltd|gmbh|solutions|logistics|technologies)", sender_email.split('@')[-1], re.IGNORECASE)
                if comp_match2:
                    company = sender_email.split('@')[-1].split('.')[0].capitalize()

        # Heuristic SAP Relevance Check
        sap_keywords = [r"\bsap\b", r"\btcode\b", r"\bva01\b", r"\bme21n\b", r"\bfb01\b", r"\bst22\b", r"\bsu53\b", r"\bprd\b", r"\bdev\b", r"\bqas\b", r"\babap\b", r"\bincident\b", r"\bticket\b", r"\bjoule\b"]
        has_sap = any(re.search(pat, combined_text, re.IGNORECASE) for pat in sap_keywords)
        
        non_sap_senders = ["redditmail.com", "daily.dev", "newsletter", "marketing", "no-reply", "noreply"]
        is_marketing = any(ns in sender_email.lower() or ns in subject.lower() for ns in non_sap_senders)

        is_sap_incident = has_sap if (has_sap or not is_marketing) else False

        desc = email_body.strip() if email_body.strip() else f"Issue reported in {system_id} system: {error_msg}"

        return ExtractionResult(
            is_sap_incident=is_sap_incident,
            relevance_reason="Contains valid SAP system/transaction details" if is_sap_incident else "Non-SAP promotional/marketing email",
            customer_name=cust_name or sender_name or "Valued Customer",
            customer_email=sender_email or "customer@enterprise.com",
            company_name=company or "Enterprise Client",
            system_id=system_id,
            client=client,
            component=component,
            tcode=tcode,
            category="Service Outage" if "joule" in lower_text else ("Configuration Error" if "not allowed" in error_msg.lower() else "Incident"),
            priority=priority,
            problem_description=desc,
            error_code=error_code,
            error_message=error_msg,
            attachment_details=ocr_text.strip() if ocr_text.strip() else "No attachments provided."
        )

llm_extractor = LLMExtractorService()
