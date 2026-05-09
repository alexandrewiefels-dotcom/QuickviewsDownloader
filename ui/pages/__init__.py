# ui/pages/__init__.py
from ui.pages.faq import render_faq_page
from ui.pages.contact import render_contact_page

__all__ = [
    'render_faq_page',
    'render_contact_page'
]
