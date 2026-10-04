"""Navigate primary parents before selecting contextual links in native browser QA."""

from playwright.sync_api import expect

PARENTS = {
    "Chat": [
        "Example conversations",
        "HR workspace",
        "Live HR workspace",
        "Approvals",
        "Test outbox",
        "Playground",
    ],
    "Logs": ["Overview", "Operations", "Security timeline", "Department usage", "Audit export"],
    "Workflow": [
        "Pipeline",
        "Catalog",
        "Policy studio",
        "Threat feed",
        "Standards evidence",
        "Threat controls",
    ],
}


class WorkspaceNavigation:
    def __init__(self, page):
        self.page = page

    def get_by_role(self, role, *, name, exact=False, **kwargs):
        primary = self.page.get_by_role("navigation", name="Main navigation")
        if name in PARENTS:
            return primary.get_by_role(role, name=name, exact=True, **kwargs)
        parent = next(key for key, names in PARENTS.items() if name in names)
        current = primary.get_by_role("link", name=parent, exact=True)
        if current.get_attribute("aria-current") != "page":
            current.click()
            expect(current).to_have_attribute("aria-current", "page")
        label = {"Overview": "Operations", "HR workspace": "Live HR workspace"}.get(name, name)
        return self.page.locator("#context-nav").get_by_role(
            role, name=label, exact=exact, **kwargs
        )


def navigation(page):
    return WorkspaceNavigation(page)
