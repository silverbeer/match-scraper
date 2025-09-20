import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://www.mlssoccer.com/mlsnext/schedule/homegrown-division/")
    page.get_by_role("button", name="Accept & Continue").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("textbox", name="Match Date").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("cell", name="12").first.click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("cell", name="15").first.click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Apply").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Age Group U13").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Age Group U13").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Age Group U13").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Age Group U13").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Division Central").click()
    page.close()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
