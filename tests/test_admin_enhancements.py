"""
Test file for 9 Admin Panel Enhancements:
1. Admin login exit intent (no popup on /admin/* paths)
2. Ebook edit with PDF upload
3. Payment management (tabs + CSV export)
4. Coupon system (discount type + ebook applicability)
5. Blog view modal + image upload
6. Affiliates input text color fix
7. Dashboard monthly revenue card
8. Ebook-wise sales analytics
9. Affiliate dashboard metrics
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://knowledge-hub-test-1.preview.emergentagent.com').rstrip('/')


class TestAdminAuth:
    """Admin authentication tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session for authenticated requests"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
    def test_admin_login_success(self):
        """Test admin login with valid credentials"""
        response = self.session.post(f"{BASE_URL}/api/auth/admin-login", json={
            "email": "admin@vigyaankart.com",
            "password": "Jaikrish@321#"
        })
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert "token" in data
        assert data["user"]["role"] == "admin"
        assert data["user"]["email"] == "admin@vigyaankart.com"

    def test_admin_login_invalid_credentials(self):
        """Test admin login with invalid credentials"""
        response = self.session.post(f"{BASE_URL}/api/auth/admin-login", json={
            "email": "admin@vigyaankart.com",
            "password": "WrongPassword"
        })
        assert response.status_code == 401


class TestAdminDashboard:
    """Test dashboard enhancements - monthly_revenue and affiliate_stats"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and setup session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        response = self.session.post(f"{BASE_URL}/api/auth/admin-login", json={
            "email": "admin@vigyaankart.com",
            "password": "Jaikrish@321#"
        })
        assert response.status_code == 200, "Admin login failed"
        
    def test_dashboard_returns_monthly_revenue(self):
        """Test that dashboard returns monthly_revenue in overview"""
        response = self.session.get(f"{BASE_URL}/api/admin/dashboard")
        assert response.status_code == 200
        data = response.json()
        
        # Check overview contains monthly_revenue
        assert "overview" in data
        assert "monthly_revenue" in data["overview"]
        assert isinstance(data["overview"]["monthly_revenue"], (int, float))
        
        # Also check other required fields
        assert "total_revenue" in data["overview"]
        assert "daily_revenue" in data["overview"]
        assert "total_orders" in data["overview"]
        assert "total_users" in data["overview"]
        assert "total_ebooks" in data["overview"]
        
    def test_dashboard_returns_affiliate_stats(self):
        """Test that dashboard returns affiliate_stats field"""
        response = self.session.get(f"{BASE_URL}/api/admin/dashboard")
        assert response.status_code == 200
        data = response.json()
        
        # Check affiliate_stats is present
        assert "affiliate_stats" in data
        assert "total_affiliates" in data["affiliate_stats"]
        assert "total_commission" in data["affiliate_stats"]
        assert isinstance(data["affiliate_stats"]["total_affiliates"], int)
        assert isinstance(data["affiliate_stats"]["total_commission"], (int, float))
        
    def test_dashboard_returns_payment_stats(self):
        """Test that dashboard returns payment_stats"""
        response = self.session.get(f"{BASE_URL}/api/admin/dashboard")
        assert response.status_code == 200
        data = response.json()
        
        assert "payment_stats" in data
        assert "successful" in data["payment_stats"]
        assert "failed" in data["payment_stats"]
        assert "success_rate" in data["payment_stats"]


class TestPaymentManagement:
    """Test payment management: all-payments endpoint, status filtering"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and setup session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        response = self.session.post(f"{BASE_URL}/api/auth/admin-login", json={
            "email": "admin@vigyaankart.com",
            "password": "Jaikrish@321#"
        })
        assert response.status_code == 200, "Admin login failed"
        
    def test_all_payments_returns_enriched_data(self):
        """Test GET /api/admin/all-payments returns enriched payment data"""
        response = self.session.get(f"{BASE_URL}/api/admin/all-payments")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # If payments exist, verify structure
        if len(data) > 0:
            payment = data[0]
            assert "order_id" in payment
            assert "customer_name" in payment
            assert "email" in payment
            assert "phone" in payment
            assert "ebook_title" in payment
            assert "amount" in payment
            assert "status" in payment
            
    def test_payments_filter_by_completed(self):
        """Test GET /api/admin/all-payments?status=completed filters correctly"""
        response = self.session.get(f"{BASE_URL}/api/admin/all-payments?status=completed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # All returned payments should have completed status
        for payment in data:
            assert payment["status"] == "completed"
            
    def test_payments_filter_by_failed(self):
        """Test GET /api/admin/all-payments?status=failed filters correctly"""
        response = self.session.get(f"{BASE_URL}/api/admin/all-payments?status=failed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # All returned payments should have failed status
        for payment in data:
            assert payment["status"] == "failed"


class TestEbookSalesAnalytics:
    """Test ebook-wise sales analytics endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and setup session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        response = self.session.post(f"{BASE_URL}/api/auth/admin-login", json={
            "email": "admin@vigyaankart.com",
            "password": "Jaikrish@321#"
        })
        assert response.status_code == 200, "Admin login failed"
        
    def test_ebook_sales_analytics_endpoint(self):
        """Test GET /api/admin/ebook-sales-analytics returns per-ebook metrics"""
        response = self.session.get(f"{BASE_URL}/api/admin/ebook-sales-analytics")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1, "Should return at least one ebook analytics"
        
        # Verify data structure for each ebook
        for ebook in data:
            assert "ebook_id" in ebook
            assert "title" in ebook
            assert "daily_sales" in ebook
            assert "monthly_sales" in ebook
            assert "total_sales" in ebook
            assert "daily_revenue" in ebook
            assert "monthly_revenue" in ebook
            assert "total_revenue" in ebook


class TestFileUploads:
    """Test PDF and image upload endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and setup session"""
        self.session = requests.Session()
        response = self.session.post(f"{BASE_URL}/api/auth/admin-login", json={
            "email": "admin@vigyaankart.com",
            "password": "Jaikrish@321#"
        })
        assert response.status_code == 200, "Admin login failed"
        
    def test_pdf_upload_success(self):
        """Test POST /api/admin/upload/pdf accepts PDF files"""
        # Create a minimal PDF content
        pdf_content = b"%PDF-1.4\n"
        files = {"file": ("test.pdf", pdf_content, "application/pdf")}
        response = self.session.post(f"{BASE_URL}/api/admin/upload/pdf", files=files)
        assert response.status_code == 200
        data = response.json()
        assert "path" in data
        assert "filename" in data
        assert data["filename"] == "test.pdf"
        
    def test_pdf_upload_rejects_non_pdf(self):
        """Test POST /api/admin/upload/pdf rejects non-PDF files"""
        txt_content = b"not a pdf file"
        files = {"file": ("test.txt", txt_content, "text/plain")}
        response = self.session.post(f"{BASE_URL}/api/admin/upload/pdf", files=files)
        assert response.status_code == 400
        data = response.json()
        assert "Only PDF files are allowed" in data.get("detail", "")
        
    def test_image_upload_success(self):
        """Test POST /api/admin/upload/image accepts image files"""
        # Minimal PNG header
        png_content = b"\x89PNG\r\n\x1a\n"
        files = {"file": ("test.png", png_content, "image/png")}
        response = self.session.post(f"{BASE_URL}/api/admin/upload/image", files=files)
        assert response.status_code == 200
        data = response.json()
        assert "path" in data
        assert "filename" in data
        assert data["filename"] == "test.png"
        
    def test_image_upload_rejects_non_image(self):
        """Test POST /api/admin/upload/image rejects non-image files"""
        txt_content = b"not an image"
        files = {"file": ("test.txt", txt_content, "text/plain")}
        response = self.session.post(f"{BASE_URL}/api/admin/upload/image", files=files)
        assert response.status_code == 400


class TestCouponSystem:
    """Test coupon system with discount_type and applicable_ebooks"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and setup session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        response = self.session.post(f"{BASE_URL}/api/auth/admin-login", json={
            "email": "admin@vigyaankart.com",
            "password": "Jaikrish@321#"
        })
        assert response.status_code == 200, "Admin login failed"
        
    def test_create_percentage_coupon(self):
        """Test creating a coupon with percentage discount type"""
        code = f"TEST_PCT_{uuid.uuid4().hex[:6].upper()}"
        response = self.session.post(f"{BASE_URL}/api/admin/coupons", json={
            "code": code,
            "discount_type": "percentage",
            "discount_value": 15,
            "max_uses": 50,
            "min_amount": 500
        })
        assert response.status_code == 200
        data = response.json()
        assert "coupon_id" in data
        
        # Verify coupon was created with correct discount_type
        coupons_response = self.session.get(f"{BASE_URL}/api/admin/coupons")
        assert coupons_response.status_code == 200
        coupons = coupons_response.json()
        created = next((c for c in coupons if c["code"] == code), None)
        assert created is not None
        assert created["discount_type"] == "percentage"
        assert created["discount_value"] == 15
        
    def test_create_fixed_coupon(self):
        """Test creating a coupon with fixed amount discount type"""
        code = f"TEST_FIX_{uuid.uuid4().hex[:6].upper()}"
        response = self.session.post(f"{BASE_URL}/api/admin/coupons", json={
            "code": code,
            "discount_type": "fixed",
            "discount_value": 200,
            "max_uses": 100
        })
        assert response.status_code == 200
        
    def test_create_coupon_with_applicable_ebooks(self):
        """Test creating a coupon with specific ebook applicability"""
        # First get an ebook ID
        ebooks_response = self.session.get(f"{BASE_URL}/api/admin/ebooks")
        assert ebooks_response.status_code == 200
        ebooks = ebooks_response.json()
        
        if len(ebooks) > 0:
            ebook_id = ebooks[0]["ebook_id"]
            code = f"TEST_APP_{uuid.uuid4().hex[:6].upper()}"
            response = self.session.post(f"{BASE_URL}/api/admin/coupons", json={
                "code": code,
                "discount_type": "percentage",
                "discount_value": 10,
                "applicable_ebooks": [ebook_id]
            })
            assert response.status_code == 200
            
            # Verify coupon has applicable_ebooks set
            coupons_response = self.session.get(f"{BASE_URL}/api/admin/coupons")
            coupons = coupons_response.json()
            created = next((c for c in coupons if c["code"] == code), None)
            assert created is not None
            assert ebook_id in created["applicable_ebooks"]


class TestEbookManagement:
    """Test ebook management with edit and PDF upload"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and setup session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        response = self.session.post(f"{BASE_URL}/api/auth/admin-login", json={
            "email": "admin@vigyaankart.com",
            "password": "Jaikrish@321#"
        })
        assert response.status_code == 200, "Admin login failed"
        
    def test_get_all_ebooks_admin(self):
        """Test admin can fetch all ebooks"""
        response = self.session.get(f"{BASE_URL}/api/admin/ebooks")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        
    def test_update_ebook(self):
        """Test admin can update ebook"""
        # Get an ebook first
        ebooks_response = self.session.get(f"{BASE_URL}/api/admin/ebooks")
        ebooks = ebooks_response.json()
        
        if len(ebooks) > 0:
            ebook_id = ebooks[0]["ebook_id"]
            original_title = ebooks[0]["title"]
            
            # Update ebook
            response = self.session.put(f"{BASE_URL}/api/admin/ebooks/{ebook_id}", json={
                "income_potential": "₹10L - ₹50L per month"  # Update a field
            })
            assert response.status_code == 200
            
            # Verify update
            updated_ebooks = self.session.get(f"{BASE_URL}/api/admin/ebooks").json()
            updated = next((e for e in updated_ebooks if e["ebook_id"] == ebook_id), None)
            assert updated is not None
            assert updated["income_potential"] == "₹10L - ₹50L per month"


class TestBlogManagement:
    """Test blog management with view and image upload"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and setup session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        response = self.session.post(f"{BASE_URL}/api/auth/admin-login", json={
            "email": "admin@vigyaankart.com",
            "password": "Jaikrish@321#"
        })
        assert response.status_code == 200, "Admin login failed"
        
    def test_get_all_blog_posts_admin(self):
        """Test admin can fetch all blog posts including content"""
        response = self.session.get(f"{BASE_URL}/api/admin/blog")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Verify posts have full content (for view modal)
        if len(data) > 0:
            post = data[0]
            assert "title" in post
            assert "content" in post
            assert "cover_image" in post
            assert "created_at" in post


class TestAffiliateSettings:
    """Test affiliate settings input fields"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and setup session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        response = self.session.post(f"{BASE_URL}/api/auth/admin-login", json={
            "email": "admin@vigyaankart.com",
            "password": "Jaikrish@321#"
        })
        assert response.status_code == 200, "Admin login failed"
        
    def test_get_affiliate_settings(self):
        """Test getting affiliate settings"""
        response = self.session.get(f"{BASE_URL}/api/admin/affiliate-settings")
        assert response.status_code == 200
        data = response.json()
        assert "commission_percent" in data
        assert "min_payout" in data
        
    def test_update_affiliate_settings(self):
        """Test updating affiliate settings"""
        response = self.session.put(f"{BASE_URL}/api/admin/affiliate-settings", json={
            "commission_percent": 12,
            "min_payout": 1000
        })
        assert response.status_code == 200
        
        # Verify update
        get_response = self.session.get(f"{BASE_URL}/api/admin/affiliate-settings")
        settings = get_response.json()
        assert settings["commission_percent"] == 12
        assert settings["min_payout"] == 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
