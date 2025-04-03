# Generated by Selenium IDE
import pytest
import time
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support import expected_conditions as EC

class TestLogin():
  def setup_method(self, method):
    self.driver = webdriver.Chrome()
    self.vars = {}
  
  def teardown_method(self, method):
    self.driver.quit()
  
  def test_login(self):
    self.driver.get("http://127.0.0.1:5000/")
    self.driver.find_element(By.LINK_TEXT, "Profile").click()
    self.driver.find_element(By.LINK_TEXT, "Login with Spotify").click()
    self.driver.find_element(By.ID, "login-username").send_keys("daniltysacnyj88@gmail.com")  # i need to use real, but nah
    self.driver.find_element(By.ID, "login-password").send_keys("testpassword1!")
    
    wait = WebDriverWait(self.driver, 10)

    login_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".ButtonInner-sc-14ud5tc-0")))
    login_button.click()
    print("clicked login button")
    time.sleep(2)

    continue_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".ButtonInner-sc-14ud5tc-0")))
    continue_button.click()
    print("clicked continue button")
    time.sleep(2)
    expected_url = "http://127.0.0.1:5000/spotify/recommendations"  # redirect if login is successful
    assert self.driver.current_url == expected_url, f"Expected URL: {expected_url}, but got {self.driver.current_url}"