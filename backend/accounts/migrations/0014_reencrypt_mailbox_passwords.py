from django.db import migrations


def reencrypt(apps, schema_editor):
    from accounts.mailbox_secrets import encrypt_mailbox_secret

    StaffMailbox = apps.get_model("accounts", "StaffMailbox")
    for mailbox in StaffMailbox.objects.exclude(imap_password="").only("pk", "imap_password"):
        sealed = encrypt_mailbox_secret(mailbox.imap_password)
        if sealed != mailbox.imap_password:
            StaffMailbox.objects.filter(pk=mailbox.pk).update(imap_password=sealed)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_staffvpbxprofile_uis_employee_id"),
    ]

    operations = [
        migrations.RunPython(reencrypt, migrations.RunPython.noop),
    ]
