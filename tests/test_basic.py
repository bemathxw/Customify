def test_simple():
    assert True

def test_home_page(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b"Home Page" in response.data

def test_profile_page(client):
    response = client.get('/profile')
    assert response.status_code == 200
    assert b"Profile Page" in response.data 