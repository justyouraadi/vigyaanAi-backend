"""
Backend API Tests for Blog, Contact, and Admin Features
Testing new features: Blog system, Contact form, Admin blog management
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthAndBasicEndpoints:
    """Health check and basic endpoint tests"""
    
    def test_api_health(self):
        """Test that the API is responding"""
        response = requests.get(f"{BASE_URL}/api/ebooks/")
        assert response.status_code == 200, f"API health check failed: {response.status_code}"
        print("✓ API is responding correctly")


class TestBlogAPI:
    """Blog endpoint tests - GET /api/blog/*"""
    
    def test_get_all_blog_posts(self):
        """Test GET /api/blog/posts returns all published posts"""
        response = requests.get(f"{BASE_URL}/api/blog/posts")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list of posts"
        print(f"✓ GET /api/blog/posts returned {len(data)} posts")
        return data
    
    def test_blog_posts_have_required_fields(self):
        """Test that blog posts have required fields"""
        response = requests.get(f"{BASE_URL}/api/blog/posts")
        assert response.status_code == 200
        posts = response.json()
        if len(posts) > 0:
            post = posts[0]
            required_fields = ['post_id', 'title', 'slug', 'excerpt', 'cover_image', 'category', 'read_time']
            for field in required_fields:
                assert field in post, f"Missing field: {field}"
            print(f"✓ Blog posts have all required fields")
        else:
            print("⚠ No blog posts to check fields")
    
    def test_get_blog_post_by_slug(self):
        """Test GET /api/blog/posts/{slug} returns a single post with content"""
        # First get all posts to find a valid slug
        posts_response = requests.get(f"{BASE_URL}/api/blog/posts")
        posts = posts_response.json()
        
        if len(posts) > 0:
            slug = posts[0]['slug']
            response = requests.get(f"{BASE_URL}/api/blog/posts/{slug}")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            post = response.json()
            assert 'content' in post, "Single post should include content"
            assert post['slug'] == slug, "Slug should match"
            print(f"✓ GET /api/blog/posts/{slug} returned post with content")
        else:
            pytest.skip("No posts available to test")
    
    def test_get_blog_post_invalid_slug(self):
        """Test GET /api/blog/posts/{invalid_slug} returns 404"""
        response = requests.get(f"{BASE_URL}/api/blog/posts/invalid-slug-that-does-not-exist-12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Invalid slug returns 404")
    
    def test_get_blog_categories(self):
        """Test GET /api/blog/categories returns categories list"""
        response = requests.get(f"{BASE_URL}/api/blog/categories")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        categories = response.json()
        assert isinstance(categories, list), "Expected list of categories"
        print(f"✓ GET /api/blog/categories returned {len(categories)} categories: {categories}")
        return categories
    
    def test_blog_posts_filter_by_category(self):
        """Test filtering blog posts by category"""
        # First get categories
        cat_response = requests.get(f"{BASE_URL}/api/blog/categories")
        categories = cat_response.json()
        
        if len(categories) > 0:
            category = categories[0]
            response = requests.get(f"{BASE_URL}/api/blog/posts?category={category}")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            posts = response.json()
            # All posts should have the filtered category
            for post in posts:
                assert post['category'] == category, f"Post category mismatch"
            print(f"✓ Category filter '{category}' working correctly, returned {len(posts)} posts")
        else:
            pytest.skip("No categories available to test")


class TestContactAPI:
    """Contact form endpoint tests"""
    
    def test_contact_submit_success(self):
        """Test POST /api/contact/submit with valid data"""
        payload = {
            "name": f"TEST_User_{uuid.uuid4().hex[:6]}",
            "email": "testuser@example.com",
            "subject": "Test Subject",
            "message": "This is a test message from automated testing."
        }
        response = requests.post(
            f"{BASE_URL}/api/contact/submit",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
        data = response.json()
        assert 'message' in data, "Response should contain message"
        print(f"✓ POST /api/contact/submit returned: {data.get('message', '')}")
    
    def test_contact_submit_missing_fields(self):
        """Test POST /api/contact/submit with missing required fields"""
        payload = {
            "name": "",
            "email": "",
            "message": ""
        }
        response = requests.post(
            f"{BASE_URL}/api/contact/submit",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400, f"Expected 400 for missing fields, got {response.status_code}"
        print("✓ Contact form validation working - rejects empty fields")
    
    def test_contact_submit_partial_data(self):
        """Test POST /api/contact/submit with only name and email (missing message)"""
        payload = {
            "name": "Test User",
            "email": "test@example.com"
            # missing message
        }
        response = requests.post(
            f"{BASE_URL}/api/contact/submit",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        # Should fail because message is required
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Contact form requires message field")


class TestAdminAuth:
    """Admin authentication tests"""
    
    def test_admin_login_success(self):
        """Test POST /api/auth/admin-login with valid credentials"""
        payload = {
            "email": "admin@vigyaankart.com",
            "password": "Admin@123"
        }
        response = requests.post(
            f"{BASE_URL}/api/auth/admin-login",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
        data = response.json()
        assert 'token' in data, "Response should contain token"
        assert 'user' in data, "Response should contain user"
        assert data['user']['role'] == 'admin', "User should have admin role"
        print(f"✓ Admin login successful, token received")
        return data['token']
    
    def test_admin_login_invalid_credentials(self):
        """Test POST /api/auth/admin-login with invalid credentials"""
        payload = {
            "email": "admin@vigyaankart.com",
            "password": "wrongpassword"
        }
        response = requests.post(
            f"{BASE_URL}/api/auth/admin-login",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Invalid admin credentials rejected")


class TestAdminBlogManagement:
    """Admin blog CRUD operations"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        payload = {
            "email": "admin@vigyaankart.com",
            "password": "Admin@123"
        }
        response = requests.post(
            f"{BASE_URL}/api/auth/admin-login",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Admin authentication failed - skipping admin tests")
    
    def test_admin_get_all_blog_posts(self, admin_token):
        """Test GET /api/admin/blog returns all posts (including unpublished)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog",
            headers={"Authorization": f"Bearer {admin_token}"},
            cookies={"session_token": admin_token}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        posts = response.json()
        assert isinstance(posts, list), "Expected list of posts"
        print(f"✓ Admin GET /api/admin/blog returned {len(posts)} posts")
    
    def test_admin_create_blog_post(self, admin_token):
        """Test POST /api/admin/blog creates a new post"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "title": f"TEST_Post_{unique_id}",
            "slug": f"test-post-{unique_id}",
            "excerpt": "Test excerpt for automated testing",
            "content": "## Test Content\n\nThis is test content.",
            "cover_image": "https://images.unsplash.com/photo-1516321318423-f06f85e504b3",
            "category": "Testing",
            "tags": ["test", "automated"],
            "read_time": 3,
            "is_published": False
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/blog",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            cookies={"session_token": admin_token}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
        data = response.json()
        assert 'post_id' in data, "Response should contain post_id"
        print(f"✓ Admin created blog post with ID: {data['post_id']}")
        return data['post_id']
    
    def test_admin_update_blog_post(self, admin_token):
        """Test PUT /api/admin/blog/{post_id} updates a post"""
        # First create a post
        unique_id = uuid.uuid4().hex[:8]
        create_payload = {
            "title": f"TEST_Update_{unique_id}",
            "slug": f"test-update-{unique_id}",
            "excerpt": "Original excerpt",
            "content": "Original content",
            "category": "Testing",
            "is_published": False
        }
        create_response = requests.post(
            f"{BASE_URL}/api/admin/blog",
            json=create_payload,
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            cookies={"session_token": admin_token}
        )
        post_id = create_response.json().get('post_id')
        
        # Now update it
        update_payload = {
            "title": f"TEST_Updated_{unique_id}",
            "excerpt": "Updated excerpt"
        }
        response = requests.put(
            f"{BASE_URL}/api/admin/blog/{post_id}",
            json=update_payload,
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            cookies={"session_token": admin_token}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
        print(f"✓ Admin updated blog post {post_id}")
        
        # Cleanup - delete the post
        requests.delete(
            f"{BASE_URL}/api/admin/blog/{post_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            cookies={"session_token": admin_token}
        )
    
    def test_admin_delete_blog_post(self, admin_token):
        """Test DELETE /api/admin/blog/{post_id} deletes a post"""
        # First create a post
        unique_id = uuid.uuid4().hex[:8]
        create_payload = {
            "title": f"TEST_Delete_{unique_id}",
            "slug": f"test-delete-{unique_id}",
            "excerpt": "To be deleted",
            "content": "Delete me",
            "category": "Testing",
            "is_published": False
        }
        create_response = requests.post(
            f"{BASE_URL}/api/admin/blog",
            json=create_payload,
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            cookies={"session_token": admin_token}
        )
        post_id = create_response.json().get('post_id')
        
        # Delete the post
        response = requests.delete(
            f"{BASE_URL}/api/admin/blog/{post_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            cookies={"session_token": admin_token}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ Admin deleted blog post {post_id}")
        
        # Verify it's deleted
        get_response = requests.get(f"{BASE_URL}/api/blog/posts/{create_payload['slug']}")
        assert get_response.status_code == 404, "Deleted post should return 404"
        print("✓ Verified post was deleted")


class TestAdminAnalytics:
    """Admin analytics endpoint tests"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        payload = {
            "email": "admin@vigyaankart.com",
            "password": "Admin@123"
        }
        response = requests.post(
            f"{BASE_URL}/api/auth/admin-login",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Admin authentication failed - skipping admin tests")
    
    def test_admin_analytics_revenue(self, admin_token):
        """Test GET /api/admin/analytics/revenue returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/analytics/revenue",
            headers={"Authorization": f"Bearer {admin_token}"},
            cookies={"session_token": admin_token}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of revenue data"
        print(f"✓ GET /api/admin/analytics/revenue returned {len(data)} data points")
    
    def test_admin_dashboard(self, admin_token):
        """Test GET /api/admin/dashboard returns overview data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/dashboard",
            headers={"Authorization": f"Bearer {admin_token}"},
            cookies={"session_token": admin_token}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert 'overview' in data, "Should contain overview"
        assert 'payment_stats' in data, "Should contain payment_stats"
        print(f"✓ Admin dashboard data retrieved successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
