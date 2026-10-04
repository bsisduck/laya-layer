"""Open the responsive menu before repository-native navigation interactions."""


def navigation(page):
    opener = page.get_by_role("button", name="Open navigation", exact=True)
    if opener.is_visible() and opener.get_attribute("aria-expanded") != "true":
        opener.click()
    return page.get_by_role("navigation", name="Main navigation")
