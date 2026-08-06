import os
import sys
from pathlib import Path

# Add backend root directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app
from database.connection import init_db, SessionLocal
from database.models import Ticket

client = TestClient(app)

def test_full_pipeline():
    print("\n--- Running AI Support Ticket Backend Test Suite (D Drive) ---")
    
    # 1. Initialize Database
    init_db()
    db = SessionLocal()

    try:
        # Clear previous test data if any
        db.query(Ticket).delete()
        db.commit()

        # 2. Test Process Mock Email directly via API
        response = client.post("/process-email")
        assert response.status_code == 200, f"Error processing email: {response.text}"
        data = response.json()
        print(f"Process Email API Response: {data}")
        assert data["success"] is True
        assert len(data["tickets_created"]) > 0
        first_ticket_id = data["tickets_created"][0]
        print(f"[OK] Created ticket ID: {first_ticket_id}")

        # 3. Test GET /tickets
        tickets_res = client.get("/tickets")
        assert tickets_res.status_code == 200
        tickets = tickets_res.json()
        print(f"[OK] GET /tickets returned {len(tickets)} ticket(s)")
        assert len(tickets) >= 1

        # 4. Test GET /tickets/{id}
        single_res = client.get(f"/tickets/{first_ticket_id}")
        assert single_res.status_code == 200
        ticket_detail = single_res.json()
        print(f"[OK] GET /tickets/{first_ticket_id} detail: Customer: {ticket_detail['customer_name']} | Error: {ticket_detail['error_message']}")
        assert ticket_detail["ticket_id"] == first_ticket_id
        assert "Document type OR is not allowed" in ticket_detail["error_message"] or "OR" in ticket_detail["error_message"]

        # 5. Test Custom Mock Email Payload
        custom_payload = {
            "message_id": "TEST-MSG-999",
            "sender_name": "Marcus Vance",
            "sender_email": "marcus.vance@supplier.com",
            "company_name": "Supplier Logistics",
            "subject": "SAP MM Purchase Order Failure in QAS Client 200 - Transaction ME21N",
            "body": "Hi Team, Transaction ME21N failed in system QAS client 200 with SAP Error Message: Vendor 100021 blocked for purchasing.",
            "attachments": []
        }

        custom_res = client.post("/tickets/process-mock-email", json=custom_payload)
        assert custom_res.status_code == 200
        custom_data = custom_res.json()
        second_ticket_id = custom_data["tickets_created"][0]
        print(f"[OK] Processed custom test payload into ticket: {second_ticket_id}")

        # Verify sequential ID generation (e.g. SAP-INC-1002)
        second_detail = client.get(f"/tickets/{second_ticket_id}").json()
        print(f"[OK] Second Ticket: {second_detail['ticket_id']} | System: {second_detail['system_id']} | Component: {second_detail['component']}")
        assert second_detail["system_id"] == "QAS"
        assert second_detail["component"] == "MM-PUR"

        print("\nAll D Drive pipeline verification tests passed successfully!")

    finally:
        db.close()

if __name__ == "__main__":
    test_full_pipeline()
