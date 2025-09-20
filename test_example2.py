import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://www.mlssoccer.com/mlsnext/schedule/homegrown-division/")
    page.get_by_role("button", name="Accept & Continue").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Age Group U13").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Age Group U13").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Age Group U13").click(button="right")
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Age Group U13").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Club Nothing Selected").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_text("Competition Nothing selected").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.locator("label").filter(has_text="Competition Nothing selected").get_by_role("listbox").select_option("28")
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Competition MLS NEXT Flex").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Competition MLS NEXT Flex").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_text("Age Group Nothing selected").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.locator("label").filter(has_text="Age Group Nothing selected").get_by_role("listbox").select_option("21")
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_text("Age Group Nothing selected").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.locator("html").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("textbox", name="Match Date").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("cell", name="12").first.click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("cell", name="15").first.click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Apply").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Competition MLS NEXT Flex").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_text("Competition MLS NEXT Flex MLS").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_text("Competition MLS NEXT Flex MLS").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_text("Competition MLS NEXT Flex MLS").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Competition MLS NEXT Flex").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Competition MLS NEXT Flex").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Division Central").click()
    page.get_by_role("main", name="Page main content").locator("iframe").content_frame.get_by_role("button", name="Division Central").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
