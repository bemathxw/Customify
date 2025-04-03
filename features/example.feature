Feature: Spotify Profile Access

  Scenario: Authenticated user can access profile page
    Given the user is authenticated
    When the user accesses the profile page
    Then the response status should be 200
    And the response should contain "Profile Page"
