from behave import given, when, then
from unittest.mock import patch, MagicMock

@given("the user is authenticated")
def step_user_authenticated(context):
    with context.client.session_transaction() as sess:
        sess['spotify_token'] = 'valid_token'
        sess['spotify_token_expires_in'] = 9999999999

@when('the user accesses the profile page')
def step_access_profile(context):
    context.response = context.client.get('/profile')

@then("the response status should be {status:d}")
def step_check_response_status(context, status):
    assert context.response.status_code == status, f"Expected status {status}, got {context.response.status_code}"

@then('the response should contain "{text}"')
def step_check_response_contains(context, text):
    response_text = context.response.data.decode('utf-8')
    print("Response data:", response_text)  # For debugging
    assert text in response_text, f"Expected to find '{text}' in response"
