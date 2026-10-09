"""Django Admin for CRM: clients, activities, outbound email.

Importing the submodules registers every ModelAdmin with the admin site.
"""

from crm.admin.activity import ActivityAdmin
from crm.admin.call import CallAdmin
from crm.admin.client import ClientAdmin
from crm.admin.company import CompanyAdmin
from crm.admin.documents import ClientDocumentAdmin
from crm.admin.email import EmailAttachmentAdmin, EmailMessageAdmin, EmailTemplateAdmin, InboundMailboxStateAdmin
from crm.admin.inlines import ActivityInline
from crm.admin.quote import QuoteAdmin, QuoteAdminForm

__all__ = [
    "ActivityAdmin",
    "ActivityInline",
    "CallAdmin",
    "ClientAdmin",
    "ClientDocumentAdmin",
    "CompanyAdmin",
    "EmailAttachmentAdmin",
    "EmailMessageAdmin",
    "EmailTemplateAdmin",
    "InboundMailboxStateAdmin",
    "QuoteAdmin",
    "QuoteAdminForm",
]
