"""
Full End-to-End Selenium Browser Test Suite for Smart Waste Management System (SWMS).

Covers:
1. Public Homepage, Citizen Registration & Role Login / Sign Out.
2. Citizen Nearby Dustbins Locator (geolocation denied fallback & access control).
3. Citizen Complaint Submission & My Requests tracking.
4. Admin Worker Registration (Driver & Cleaner only, no Crew Leader option).
5. Admin Vehicle Registration & Dynamic Driver Allocation.
6. Admin Public Dustbin Creation (map picker + coordinates) & Verification.
7. Admin Crew Formation, Crew Details (including Allocated Vehicle Details), & Task Creation/Dispatch.
8. Worker Availability Controls (toggling ACTIVE/INACTIVE + locked when ASSIGNED).
9. Crew Leader vs. Regular Crew Member Task Permissions (Start & Complete with photo upload).
10. Admin Task Verification, Citizen Request Resolution, & Historical Crew Archive Details after Dissolution.

How to run:
  Headless (default):
    python manage.py test test_selenium_e2e --settings=config.test_settings

  Visible Chrome browser (watch it run!):
    $env:SELENIUM_HEADED="1"; python manage.py test test_selenium_e2e --settings=config.test_settings
"""

import os
import shutil
import tempfile

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from citizen_services.models import Dustbin

User = get_user_model()
TEMP_MEDIA_DIR = tempfile.mkdtemp(prefix="swms_selenium_media_")


@override_settings(MEDIA_ROOT=TEMP_MEDIA_DIR)
class FullProjectSeleniumE2ETests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp_files_dir = tempfile.mkdtemp(prefix="swms_selenium_assets_")
        cls.proof_image_path = os.path.join(cls.temp_files_dir, "proof.png")
        Image.new("RGB", (40, 40), color=(46, 125, 50)).save(cls.proof_image_path)

        options = webdriver.ChromeOptions()
        if os.getenv("SELENIUM_HEADED", "0") != "1":
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1366,900")
        options.add_argument("--disable-gpu")
        # Deny geolocation prompt automatically so Nearby Dustbins fallback path is tested cleanly
        options.add_experimental_option(
            "prefs",
            {"profile.default_content_setting_values.geolocation": 2},
        )

        cls.driver = webdriver.Chrome(options=options)
        cls.wait = WebDriverWait(
            cls.driver,
            10,
            ignored_exceptions=(StaleElementReferenceException,),
        )

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()
        shutil.rmtree(cls.temp_files_dir, ignore_errors=True)
        shutil.rmtree(TEMP_MEDIA_DIR, ignore_errors=True)
        super().tearDownClass()

    def click(self, by, value):
        el = self.wait.until(EC.element_to_be_clickable((by, value)))
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        el.click()
        return el

    def wait_for_text(self, text):
        target = text.lower()
        self.wait.until(lambda d: target in d.find_element(By.TAG_NAME, "body").text.lower())

    def login_as(self, email, password):
        self.driver.get(f"{self.live_server_url}/accounts/login/")
        self.wait.until(EC.presence_of_element_located((By.ID, "id_username"))).clear()
        self.driver.find_element(By.ID, "id_username").send_keys(email)
        self.driver.find_element(By.ID, "id_password").clear()
        self.driver.find_element(By.ID, "id_password").send_keys(password)
        self.click(By.XPATH, "//main//button[@type='submit']")

    def sign_out(self):
        self.click(By.XPATH, "//form[contains(@action, '/logout/')]//button")
        self.wait.until(EC.url_to_be(f"{self.live_server_url}/"))

    def test_entire_swms_workflow(self):
        # Pre-seed Administrator & one public Dustbin
        admin_email = "admin.e2e@example.com"
        admin_pass = "AdminPass123!"
        User.objects.create_superuser(
            username="admin_e2e",
            email=admin_email,
            password=admin_pass,
            role=User.Role.ADMINISTRATOR,
            approved=True,
        )
        Dustbin.objects.create(
            name="DBno1",
            description="Central Bus Stand Gate",
            latitude=16.833944,
            longitude=81.531444,
            is_active=True,
        )

        # ------------------------------------------------------------------
        # 1. Homepage & Citizen Self-Registration + Login
        # ------------------------------------------------------------------
        self.driver.get(self.live_server_url)
        self.assertIn("Smart Waste", self.driver.page_source)

        self.click(By.LINK_TEXT, "Citizen Register")
        self.wait.until(EC.url_contains("/accounts/register/"))

        citizen_email = "citizen.e2e@example.com"
        citizen_pass = "CitizenPass123!"
        self.driver.find_element(By.ID, "id_full_name").send_keys("Asha Citizen")
        self.driver.find_element(By.ID, "id_email").send_keys(citizen_email)
        self.driver.find_element(By.ID, "id_mobile_number").send_keys("9876543210")
        self.driver.find_element(By.ID, "id_house_number").send_keys("12-4B")
        self.driver.find_element(By.ID, "id_street_locality").send_keys("Gandhi Nagar")
        self.driver.find_element(By.ID, "id_password").send_keys(citizen_pass)
        self.driver.find_element(By.ID, "id_password_confirm").send_keys(citizen_pass)
        self.click(By.XPATH, "//main//button[@type='submit']")

        self.wait.until(EC.url_contains("/citizen/dashboard/"))
        self.assertIn("Nearby Dustbins", self.driver.page_source)

        # ------------------------------------------------------------------
        # 2. Citizen Nearby Dustbins Locator (Geolocation Denied Fallback)
        # ------------------------------------------------------------------
        self.click(By.LINK_TEXT, "Nearby Dustbins")
        self.wait.until(EC.url_contains("/citizen/nearby-dustbins/"))
        self.wait.until(EC.presence_of_element_located((By.ID, "nearby-map")))
        self.assertIn("DBno1", self.driver.page_source)
        self.assertIn("Central Bus Stand Gate", self.driver.page_source)

        # ------------------------------------------------------------------
        # 3. Citizen Submits Waste Complaint
        # ------------------------------------------------------------------
        self.click(By.LINK_TEXT, "Submit Request")
        self.wait.until(EC.url_contains("/citizen/submit/"))

        self.driver.find_element(By.ID, "id_title").send_keys("Overflowing Bin Near Market")
        Select(self.driver.find_element(By.ID, "id_cause")).select_by_visible_text("Overflowing Dustbin")
        self.driver.find_element(By.ID, "id_description").send_keys("Waste spilling onto footpath.")
        self.driver.find_element(By.ID, "id_address").send_keys("Market Road, Ward 3")
        self.driver.find_element(By.ID, "id_latitude").clear()
        self.driver.find_element(By.ID, "id_latitude").send_keys("16.835000")
        self.driver.find_element(By.ID, "id_longitude").clear()
        self.driver.find_element(By.ID, "id_longitude").send_keys("81.532000")
        self.click(By.XPATH, "//button[contains(., 'Submit Request')]")

        self.wait.until(EC.url_contains("/citizen/requests/"))
        self.assertIn("Overflowing Bin Near Market", self.driver.page_source)
        self.sign_out()

        # ------------------------------------------------------------------
        # 4. Admin Logs In -> Registers Driver & Cleaner (No Crew Leader option)
        # ------------------------------------------------------------------
        self.login_as(admin_email, admin_pass)
        self.wait.until(EC.url_contains("/operations/admin/"))

        self.click(By.LINK_TEXT, "Workers")
        self.wait.until(EC.url_contains("/operations/admin/workers/"))

        designation_select = Select(self.driver.find_element(By.ID, "id_designation"))
        designation_values = [opt.get_attribute("value") for opt in designation_select.options]
        self.assertNotIn("crew_leader", designation_values)
        self.assertEqual(set(designation_values), {"driver", "cleaner"})

        # Register Driver
        driver_email = "driver.e2e@example.com"
        worker_pass = "WorkerPass123!"
        self.driver.find_element(By.ID, "id_full_name").send_keys("Ravi Driver")
        self.driver.find_element(By.ID, "id_email").send_keys(driver_email)
        self.driver.find_element(By.ID, "id_mobile_number").send_keys("9000011111")
        Select(self.driver.find_element(By.ID, "id_designation")).select_by_value("driver")
        self.driver.find_element(By.ID, "id_worker_id").send_keys("DRV-E2E-01")
        self.driver.find_element(By.ID, "id_password").send_keys(worker_pass)
        self.click(By.XPATH, "//button[contains(., 'Register Worker')]")
        self.wait_for_text("Ravi Driver")

        # Register Cleaner
        cleaner_email = "cleaner.e2e@example.com"
        self.driver.find_element(By.ID, "id_full_name").send_keys("Sita Cleaner")
        self.driver.find_element(By.ID, "id_email").send_keys(cleaner_email)
        self.driver.find_element(By.ID, "id_mobile_number").send_keys("9000022222")
        Select(self.driver.find_element(By.ID, "id_designation")).select_by_value("cleaner")
        self.driver.find_element(By.ID, "id_worker_id").send_keys("CLN-E2E-02")
        self.driver.find_element(By.ID, "id_password").send_keys(worker_pass)
        self.click(By.XPATH, "//button[contains(., 'Register Worker')]")
        self.wait_for_text("Sita Cleaner")

        # ------------------------------------------------------------------
        # 5. Admin Registers Vehicle & Allocates Driver
        # ------------------------------------------------------------------
        self.click(By.LINK_TEXT, "Vehicles")
        self.wait.until(EC.url_contains("/operations/admin/vehicles/"))

        self.driver.find_element(By.ID, "id_registration_number").send_keys("AP39 E2E 4040")
        self.driver.find_element(By.ID, "id_vehicle_type").send_keys("Mini Tipper")
        self.click(By.XPATH, "//button[contains(., 'Register Vehicle')]")
        self.wait_for_text("AP39 E2E 4040")

        Select(self.driver.find_element(By.ID, "vehicle_id")).select_by_index(1)
        Select(self.driver.find_element(By.ID, "driver_id")).select_by_index(1)
        self.click(By.XPATH, "//button[contains(., 'Assign Driver')]")
        self.wait_for_text("In Service")
        self.assertIn("Ravi Driver", self.driver.page_source)

        # ------------------------------------------------------------------
        # 6. Admin Registers Public Dustbin (Map Picker + Manual Input)
        # ------------------------------------------------------------------
        self.click(By.LINK_TEXT, "Dustbins")
        self.wait.until(EC.url_contains("/operations/admin/dustbins/"))
        self.wait.until(EC.presence_of_element_located((By.ID, "dustbin-picker-map")))

        self.driver.find_element(By.ID, "id_name").send_keys("DB_SELENIUM_01")
        self.driver.find_element(By.ID, "id_description").send_keys("Selenium Ward 5 Junction")
        self.driver.find_element(By.ID, "id_dustbin_lat").send_keys("16.836100")
        self.driver.find_element(By.ID, "id_dustbin_lng").send_keys("81.533100")
        self.click(By.XPATH, "//button[contains(., 'Register Dustbin')]")
        self.wait_for_text("DB_SELENIUM_01")

        # ------------------------------------------------------------------
        # 7. Admin Forms Crew & Inspects Crew Details (including Allocated Vehicle)
        # ------------------------------------------------------------------
        self.click(By.LINK_TEXT, "Crews")
        self.wait.until(EC.url_contains("/operations/admin/crews/"))

        self.driver.find_element(By.ID, "crew_name").send_keys("Alpha E2E Squad")
        member_checkboxes = self.driver.find_elements(By.CSS_SELECTOR, "input[name='members']")
        for cb in member_checkboxes:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cb)
            cb.click()

        # Select Ravi Driver as Crew Leader
        leader_select = Select(self.driver.find_element(By.ID, "crew_leader"))
        for opt in leader_select.options:
            if "Ravi Driver" in opt.text:
                leader_select.select_by_visible_text(opt.text)
                break

        self.click(By.XPATH, "//button[contains(., 'Create Temporary Crew')]")
        self.wait_for_text("Alpha E2E Squad")

        # Click Crew Details and verify Allocated Vehicle Details appear!
        self.click(By.LINK_TEXT, "Details")
        self.wait.until(EC.url_contains("/operations/admin/crews/"))
        self.assertIn("Alpha E2E Squad", self.driver.page_source)
        self.assertIn("Allocated Vehicle Details (1)", self.driver.page_source)
        self.assertIn("AP39 E2E 4040", self.driver.page_source)
        self.assertIn("Mini Tipper", self.driver.page_source)

        # ------------------------------------------------------------------
        # 8. Admin Approves Citizen Request, Generates Task & Assigns to Crew
        # ------------------------------------------------------------------
        self.click(By.LINK_TEXT, "Requests")
        self.wait.until(EC.url_contains("/operations/admin/requests/"))
        self.click(By.LINK_TEXT, "Review & Action")

        self.click(By.XPATH, "//button[@value='approve']")
        self.click(By.XPATH, "//button[@value='generate_task']")
        self.wait.until(EC.url_contains("/operations/admin/tasks/"))

        crew_select = Select(self.driver.find_element(By.ID, "assigned_crew"))
        crew_select.select_by_index(1)
        self.click(By.XPATH, "//button[contains(., 'Save Assignment')]")
        self.wait_for_text("Alpha E2E Squad")
        self.sign_out()

        # ------------------------------------------------------------------
        # 9. Non-Leader Crew Member (Sita Cleaner):
        #    - Availability locked to ASSIGNED
        #    - Crew task shows "Managed by Crew Leader" (no START TASK button)
        # ------------------------------------------------------------------
        self.login_as(cleaner_email, worker_pass)
        self.wait.until(EC.url_contains("/operations/worker/"))

        self.assertIn("Status: Assigned", self.driver.page_source)
        self.assertIn("Managed by Crew Leader", self.driver.page_source)
        avail_btn = self.driver.find_element(By.XPATH, "//button[contains(., \"I'M AVAILABLE\")]")
        unavail_btn = self.driver.find_element(By.XPATH, "//button[contains(., \"I'M UNAVAILABLE\")]")
        self.assertFalse(avail_btn.is_enabled())
        self.assertFalse(unavail_btn.is_enabled())
        self.assertEqual(len(self.driver.find_elements(By.XPATH, "//button[contains(., 'START TASK')]")), 0)
        self.sign_out()

        # ------------------------------------------------------------------
        # 10. Crew Leader (Ravi Driver):
        #     - Sees YOU ARE CREW LEADER
        #     - Starts Task & Completes Task with Proof Photo + Remarks
        # ------------------------------------------------------------------
        self.login_as(driver_email, worker_pass)
        self.wait.until(EC.url_contains("/operations/worker/"))

        self.assertIn("YOU ARE CREW LEADER", self.driver.page_source)
        self.click(By.XPATH, "//button[contains(., 'START TASK')]")
        self.click(By.XPATH, "//a[contains(., 'COMPLETE TASK')]")
        self.wait.until(EC.url_contains("/complete/"))

        self.driver.find_element(By.ID, "id_completion_photo").send_keys(self.proof_image_path)
        self.driver.find_element(By.ID, "id_completion_remarks").send_keys("Cleared overflowing bin and sanitized area.")
        self.click(By.XPATH, "//button[contains(., 'Submit as Completed')]")

        self.wait.until(EC.url_contains("/operations/worker/"))
        self.assertIn("Overflowing Bin Near Market", self.driver.page_source)
        self.sign_out()

        # ------------------------------------------------------------------
        # 11. Admin Verifies Completion, Dissolves Crew & Checks Archive Details
        # ------------------------------------------------------------------
        self.login_as(admin_email, admin_pass)
        self.click(By.LINK_TEXT, "Tasks")
        self.wait.until(EC.url_contains("/operations/admin/tasks/"))

        self.click(By.LINK_TEXT, "Details / Action")
        self.wait.until(EC.presence_of_element_located((By.ID, "admin_notes"))).send_keys("Verified clean.")
        self.click(By.XPATH, "//button[contains(., 'Verify Completion')]")
        self.wait_for_text("VERIFIED BY ADMIN")

        # Dissolve Crew & Verify Historical Records Details
        self.click(By.LINK_TEXT, "Crews")
        self.wait.until(EC.url_contains("/operations/admin/crews/"))
        self.click(By.XPATH, "//button[contains(., 'Dissolve')]")
        self.wait.until(EC.alert_is_present())
        self.driver.switch_to.alert.accept()

        self.wait_for_text("Historical Crew Records")
        self.click(By.LINK_TEXT, "Details")
        self.wait_for_text("DISSOLVED")
        self.assertIn("Alpha E2E Squad", self.driver.page_source)
        self.assertIn("AP39 E2E 4040", self.driver.page_source)
        self.assertIn("Cleared overflowing bin and sanitized area.", self.driver.page_source)
        self.sign_out()

        # ------------------------------------------------------------------
        # 12. Released Worker Availability Toggle Check + Blocked from Nearby Dustbins
        # ------------------------------------------------------------------
        self.login_as(cleaner_email, worker_pass)
        self.wait.until(EC.url_contains("/operations/worker/"))
        self.assertIn("AVAILABLE (CURRENT)", self.driver.page_source)

        # Toggle to INACTIVE
        self.click(By.XPATH, "//button[contains(., \"I'M UNAVAILABLE\")]")
        self.wait_for_text("UNAVAILABLE (CURRENT)")

        # Verify worker is blocked from Citizen Nearby Dustbins
        self.driver.get(f"{self.live_server_url}/citizen/nearby-dustbins/")
        self.assertNotIn("/citizen/nearby-dustbins/", self.driver.current_url)
