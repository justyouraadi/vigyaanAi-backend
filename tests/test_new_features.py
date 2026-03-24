"""
Test suite for VigyaanKart new features:
1. Affiliate Referral System
2. AI Chat Assistant (GPT-5.2)
3. Invoice Generation
4. Upsell Recommendations
5. Email Capture (Exit Intent)
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL')

# Test admin credentials
ADMIN_EMAIL = "admin@vigyaankart.com"
ADMIN_PASSWORD = "Jaikrish@321#"


class TestAdminLogin:
    """Admin authentication tests"""
    
    def test_admin_login_success(self):
        """Admin should be able to login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/admin-login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["role"] == "admin"
        print(f"✓ Admin login successful, token received")


class TestAffiliateSystem:
    """Affiliate referral system tests"""
    
    @pytest.fixture
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        res = session.post(f"{BASE_URL}/api/auth/admin-login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if res.status_code == 200:
            token = res.json().get("token")
            session.cookies.set("session_token", token)
        return session
    
    def test_get_affiliate_settings(self, admin_session):
        """Admin can get affiliate settings"""
        response = admin_session.get(f"{BASE_URL}/api/admin/affiliate-settings")
        assert response.status_code == 200
        data = response.json()
        assert "commission_percent" in data
        assert "min_payout" in data
        print(f"✓ Affiliate settings: commission={data.get('commission_percent')}%, min_payout=₹{data.get('min_payout')}")
    
    def test_update_affiliate_settings(self, admin_session):
        """Admin can update affiliate commission settings"""
        new_settings = {"commission_percent": 15, "min_payout": 1000}
        response = admin_session.put(
            f"{BASE_URL}/api/admin/affiliate-settings",
            json=new_settings
        )
        assert response.status_code == 200
        
        # Verify update
        verify_res = admin_session.get(f"{BASE_URL}/api/admin/affiliate-settings")
        data = verify_res.json()
        assert data.get("commission_percent") == 15
        assert data.get("min_payout") == 1000
        print(f"✓ Updated affiliate settings to 15% commission, ₹1000 min payout")
        
        # Reset to default
        admin_session.put(f"{BASE_URL}/api/admin/affiliate-settings", json={
            "commission_percent": 10,
            "min_payout": 500
        })
    
    def test_get_affiliates_list(self, admin_session):
        """Admin can get list of all affiliates"""
        response = admin_session.get(f"{BASE_URL}/api/admin/affiliates")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got affiliates list: {len(data)} affiliates")
    
    def test_track_referral_valid_code(self, admin_session):
        """Track referral with valid affiliate code - should fail if no affiliates exist"""
        # First get an affiliate code if any exist
        affiliates_res = admin_session.get(f"{BASE_URL}/api/admin/affiliates")
        affiliates = affiliates_res.json()
        
        if affiliates:
            code = affiliates[0].get("referral_code")
            response = requests.get(f"{BASE_URL}/api/affiliates/track/{code}")
            assert response.status_code == 200
            data = response.json()
            assert "message" in data
            assert data.get("referral_code") == code
            print(f"✓ Tracked referral with code: {code}")
        else:
            # Test with invalid code
            response = requests.get(f"{BASE_URL}/api/affiliates/track/INVALID123")
            assert response.status_code == 404
            print("✓ No affiliates exist yet, invalid code returns 404 as expected")
    
    def test_track_referral_invalid_code(self):
        """Track referral with invalid code returns 404"""
        response = requests.get(f"{BASE_URL}/api/affiliates/track/INVALIDCODE999")
        assert response.status_code == 404
        print("✓ Invalid referral code returns 404")
    
    def test_affiliate_join_requires_auth(self):
        """Joining affiliate program requires authentication"""
        response = requests.post(f"{BASE_URL}/api/affiliates/join")
        assert response.status_code == 401
        print("✓ Affiliate join requires authentication (401)")
    
    def test_affiliate_me_requires_auth(self):
        """Getting affiliate profile requires authentication"""
        response = requests.get(f"{BASE_URL}/api/affiliates/me")
        assert response.status_code == 401
        print("✓ Affiliate /me requires authentication (401)")


class TestAIChatAssistant:
    """AI Chat Assistant (GPT-5.2) tests"""
    
    def test_chat_message_basic(self):
        """Send message to AI chat and get response"""
        response = requests.post(f"{BASE_URL}/api/chat/message", json={
            "message": "What ebooks do you have?",
            "session_id": "test_session_123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "session_id" in data
        assert data["session_id"] == "test_session_123"
        assert len(data["response"]) > 0
        print(f"✓ AI chat response received: {data['response'][:100]}...")
    
    def test_chat_message_empty(self):
        """Empty message returns error"""
        response = requests.post(f"{BASE_URL}/api/chat/message", json={
            "message": "",
            "session_id": "test_session_empty"
        })
        assert response.status_code == 400
        print("✓ Empty message returns 400 error")
    
    def test_chat_history(self):
        """Get chat history for a session"""
        session_id = f"test_history_{int(time.time())}"
        
        # First send a message
        requests.post(f"{BASE_URL}/api/chat/message", json={
            "message": "Hello",
            "session_id": session_id
        })
        time.sleep(2)  # Wait for AI response
        
        # Get history
        response = requests.get(f"{BASE_URL}/api/chat/history/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have at least user message and assistant response
        assert len(data) >= 2
        print(f"✓ Chat history returned {len(data)} messages")
    
    def test_chat_history_empty_session(self):
        """Empty session returns empty list"""
        response = requests.get(f"{BASE_URL}/api/chat/history/nonexistent_session_xyz")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0
        print("✓ Empty session returns empty history")


class TestInvoiceGeneration:
    """Invoice PDF generation tests"""
    
    def test_invoice_requires_auth(self):
        """Invoice endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/invoice/order_test123")
        assert response.status_code == 401
        print("✓ Invoice endpoint requires authentication (401)")
    
    @pytest.fixture
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        res = session.post(f"{BASE_URL}/api/auth/admin-login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if res.status_code == 200:
            token = res.json().get("token")
            session.cookies.set("session_token", token)
        return session
    
    def test_invoice_nonexistent_order(self, admin_session):
        """Invoice for non-existent order returns 404"""
        response = admin_session.get(f"{BASE_URL}/api/invoice/order_nonexistent123")
        assert response.status_code == 404
        print("✓ Invoice for non-existent order returns 404")


class TestUpsellRecommendations:
    """Upsell recommendations tests"""
    
    def test_upsell_with_valid_ebook(self):
        """Get upsell recommendations for a valid ebook"""
        # First get an ebook ID
        ebooks_res = requests.get(f"{BASE_URL}/api/ebooks/")
        ebooks = ebooks_res.json()
        
        if ebooks:
            ebook_id = ebooks[0].get("ebook_id")
            response = requests.get(f"{BASE_URL}/api/upsell/{ebook_id}")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            print(f"✓ Upsell recommendations: {len(data)} related ebooks")
        else:
            pytest.skip("No ebooks available to test upsell")
    
    def test_upsell_with_invalid_ebook(self):
        """Get upsell for non-existent ebook returns empty list"""
        response = requests.get(f"{BASE_URL}/api/upsell/nonexistent_ebook_xyz")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0
        print("✓ Upsell for non-existent ebook returns empty list")


class TestEmailCapture:
    """Exit intent email capture tests"""
    
    def test_email_capture_success(self):
        """Capture email successfully"""
        test_email = f"test_capture_{int(time.time())}@example.com"
        response = requests.post(f"{BASE_URL}/api/email-capture", json={
            "email": test_email,
            "source": "exit_intent"
        })
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"✓ Email captured: {test_email}")
    
    def test_email_capture_empty_email(self):
        """Empty email returns error"""
        response = requests.post(f"{BASE_URL}/api/email-capture", json={
            "email": "",
            "source": "exit_intent"
        })
        assert response.status_code == 400
        print("✓ Empty email returns 400 error")
    
    def test_email_capture_duplicate(self):
        """Duplicate email still returns success (idempotent)"""
        test_email = "duplicate_test@example.com"
        
        # First capture
        requests.post(f"{BASE_URL}/api/email-capture", json={
            "email": test_email,
            "source": "exit_intent"
        })
        
        # Second capture (duplicate)
        response = requests.post(f"{BASE_URL}/api/email-capture", json={
            "email": test_email,
            "source": "exit_intent"
        })
        assert response.status_code == 200
        print("✓ Duplicate email capture is idempotent")


class TestEbooksAPI:
    """Basic ebooks API tests for new features context"""
    
    def test_get_ebooks(self):
        """Get all active ebooks"""
        response = requests.get(f"{BASE_URL}/api/ebooks/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got {len(data)} ebooks")
    
    def test_get_ebook_by_slug(self):
        """Get ebook by slug"""
        # First get list
        ebooks_res = requests.get(f"{BASE_URL}/api/ebooks/")
        ebooks = ebooks_res.json()
        
        if ebooks:
            slug = ebooks[0].get("slug")
            response = requests.get(f"{BASE_URL}/api/ebooks/{slug}")
            assert response.status_code == 200
            data = response.json()
            assert data.get("slug") == slug
            print(f"✓ Got ebook by slug: {slug}")
        else:
            pytest.skip("No ebooks available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
