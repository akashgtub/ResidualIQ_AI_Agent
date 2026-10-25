import sys
import unittest
from pathlib import Path

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

# Avoid conflict with Python standard library 'code' module
if "code" in sys.modules and not hasattr(sys.modules["code"], "__path__"):
    del sys.modules["code"]

from code.config import (
    REPO_ROOT,
    DATASET_DIR,
    DELETION_REQUESTS_PATH,
    SAMPLE_DELETION_REQUESTS_PATH,
    USER_IDENTITIES_PATH,
    USER_AUDIT_LOG_PATH,
    OUTPUT_PATH,
    DeletionStatus,
    Phase,
    State,
    OPERATION_STATE_MAP,
)
from code.core.identity_resolver import IdentityResolver, UserIdentity
from code.core.intent_classifier import IntentClassifier, RequestType


class TestConfig(unittest.TestCase):
    """Verify repository paths, constants, and state mappings."""

    def test_repo_root_and_dataset_paths(self):
        self.assertTrue(REPO_ROOT.exists(), "Repository root must exist")
        self.assertTrue(DATASET_DIR.exists(), "Dataset directory must exist")
        self.assertTrue(USER_IDENTITIES_PATH.exists(), "user_identities.csv must exist")
        self.assertTrue(USER_AUDIT_LOG_PATH.exists(), "user_audit_log.csv must exist")
        self.assertTrue(DELETION_REQUESTS_PATH.exists(), "deletion_requests.csv must exist")
        self.assertTrue(SAMPLE_DELETION_REQUESTS_PATH.exists(), "sample_deletion_requests.csv must exist")

    def test_output_path(self):
        self.assertEqual(OUTPUT_PATH, REPO_ROOT / "output.csv")

    def test_operation_state_map(self):
        self.assertEqual(OPERATION_STATE_MAP["REPORT_REMAINING_RECORD"], State.PRESENT.value)
        self.assertEqual(OPERATION_STATE_MAP["DISABLE_DATA_FLOW"], State.DISABLED.value)
        self.assertEqual(OPERATION_STATE_MAP["BLOCK_RESTORE"], State.BLOCKED.value)
        self.assertEqual(OPERATION_STATE_MAP["DELETE_RECORD"], State.ABSENT.value)
        self.assertEqual(OPERATION_STATE_MAP["REDACT_RECORD"], State.REDACTED.value)
        self.assertEqual(OPERATION_STATE_MAP["ANONYMIZE_RECORD"], State.ANONYMIZED.value)
        self.assertEqual(OPERATION_STATE_MAP["VERIFY_RECORD_ABSENT"], State.ABSENT.value)
        self.assertEqual(OPERATION_STATE_MAP["VERIFY_RECORD_PRESENT"], State.PRESENT.value)


class TestIdentityResolver(unittest.TestCase):
    """Verify current and historical identity resolution without hardcoding specific cases."""

    @classmethod
    def setUpClass(cls):
        cls.resolver = IdentityResolver()
        cls.resolver.load()

    def test_loads_all_identities(self):
        users = self.resolver.get_all_users()
        self.assertGreater(len(users), 800, "Should load all users from user_identities.csv")

    def test_current_email_matching(self):
        # Pick the first loaded user dynamically
        users = self.resolver.get_all_users()
        sample_user = users[0]

        resolved = self.resolver.resolve_by_email(sample_user.current_email)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.user_id, sample_user.user_id)
        self.assertEqual(resolved.name, sample_user.name)

    def test_case_insensitive_matching(self):
        users = self.resolver.get_all_users()
        sample_user = users[0]

        upper_email = sample_user.current_email.upper()
        resolved_upper = self.resolver.resolve_by_email(upper_email)
        self.assertIsNotNone(resolved_upper)
        self.assertEqual(resolved_upper.user_id, sample_user.user_id)

        padded_email = f"   {sample_user.current_email.capitalize()}   "
        resolved_padded = self.resolver.resolve_by_email(padded_email)
        self.assertIsNotNone(resolved_padded)
        self.assertEqual(resolved_padded.user_id, sample_user.user_id)

    def test_historical_email_matching(self):
        # Find a user who has a historical email recorded in user_audit_log
        user_with_hist = None
        for u in self.resolver.get_all_users():
            if u.historical_emails:
                user_with_hist = u
                break

        self.assertIsNotNone(user_with_hist, "At least one user must have historical emails")
        old_email = user_with_hist.historical_emails[0]

        resolved = self.resolver.resolve_by_email(old_email)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.user_id, user_with_hist.user_id)
        self.assertIn(old_email.lower(), resolved.all_emails)

    def test_hash_resolution(self):
        users = self.resolver.get_all_users()
        sample_user = users[1]

        resolved = self.resolver.resolve_by_hash(sample_user.current_email_hash)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.user_id, sample_user.user_id)

    def test_phone_resolution(self):
        users = self.resolver.get_all_users()
        sample_user = users[2]

        resolved = self.resolver.resolve_by_phone(sample_user.current_phone)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.user_id, sample_user.user_id)

    def test_unknown_and_ambiguous_identities(self):
        self.assertIsNone(self.resolver.resolve_by_email("nonexistent.user.9999@unknown.domain.org"))
        self.assertIsNone(self.resolver.resolve_by_email(""))
        self.assertIsNone(self.resolver.resolve_by_email(None))
        self.assertIsNone(self.resolver.resolve_by_user_id("user_nonexistent_9999"))
        self.assertIsNone(self.resolver.resolve_by_identifier("invalid_random_string_xyz"))

    def test_all_searchable_strings(self):
        users = self.resolver.get_all_users()
        sample_user = users[0]
        searchable = sample_user.all_searchable_strings

        self.assertIn(sample_user.user_id, searchable)
        self.assertIn(sample_user.name, searchable)
        self.assertIn(sample_user.current_email, searchable)
        self.assertIn(sample_user.current_phone, searchable)
        self.assertIn(sample_user.current_email_hash, searchable)


class TestIntentClassifier(unittest.TestCase):
    """Verify deletion vs. non-deletion intent classification."""

    @classmethod
    def setUpClass(cls):
        cls.classifier = IntentClassifier()

    def test_english_deletion_requests(self):
        samples = [
            "Please permanently delete the account associated with this email address.",
            "I want to close this account and have its associated personal data deleted.",
            "Please process a permanent account-deletion request for this email address.",
            "I no longer use this account and would like it permanently deleted.",
            "Please erase the account linked to this email address.",
            "Please remove my profile and the personal details attached to it.",
        ]
        for text in samples:
            intent = self.classifier.classify(text)
            self.assertTrue(intent.is_deletion, f"Should be deletion: {text}")
            self.assertEqual(intent.request_type, RequestType.DELETION)

    def test_multilingual_deletion_requests(self):
        multilingual_samples = [
            # French
            ("Je demande la suppression définitive du compte associé à cette adresse e-mail.", "French"),
            # Spanish
            ("Solicito la eliminación permanente de la cuenta asociada a este correo.", "Spanish"),
            # Portuguese
            ("Solicito a exclusão permanente da conta associada a este e-mail.", "Portuguese"),
            # Japanese
            ("このメールアドレスに関連するアカウントの完全な削除を依頼します。", "Japanese"),
            # Korean
            ("이 이메일 주소에 연결된 계정의 영구 삭제를 요청합니다.", "Korean"),
            # German
            ("Bitte führen Sie die vollständige Löschung meines Benutzerkontos durch.", "German"),
            # Italian
            ("Richiedo la cancellazione definitiva del mio account e dei dati associati.", "Italian"),
        ]
        for text, lang in multilingual_samples:
            intent = self.classifier.classify(text)
            self.assertTrue(intent.is_deletion, f"Failed for {lang}: {text}")

    def test_non_deletion_access_requests(self):
        samples = [
            ("Can you tell me what personal information you hold about me? This is an information request, not a request to erase it.", RequestType.ACCESS),
            ("I need a copy of last year's invoices for my records. Please leave my profile and purchase history in place.", RequestType.ACCESS),
            ("Could you send me a copy of the information held on my account? I still use it, so please don't delete or change anything.", RequestType.OTHER_NON_DELETION),
        ]
        for text, expected_type in samples:
            intent = self.classifier.classify(text)
            self.assertFalse(intent.is_deletion, f"Should NOT be deletion: {text}")
            self.assertIn(intent.request_type, [RequestType.ACCESS, RequestType.OTHER_NON_DELETION])

    def test_non_deletion_correction_requests(self):
        samples = [
            ("The mobile number on my profile is out of date. Please replace it with the new one and leave the account active.", RequestType.OTHER_NON_DELETION),
            ("My surname is misspelled on the account. Can you correct it without removing any of my records?", RequestType.CORRECTION),
            ("Please change the email address used for this account. I want to continue using the service.", RequestType.OTHER_NON_DELETION),
        ]
        for text, expected_type in samples:
            intent = self.classifier.classify(text)
            self.assertFalse(intent.is_deletion, f"Should NOT be deletion: {text}")
            self.assertIn(intent.request_type, [expected_type, RequestType.CORRECTION, RequestType.OTHER_NON_DELETION])

    def test_non_deletion_export_requests(self):
        text = "I'd like to download my account information in a portable format. Please keep the account as it is."
        intent = self.classifier.classify(text)
        self.assertFalse(intent.is_deletion)
        self.assertIn(intent.request_type, [RequestType.EXPORT, RequestType.OTHER_NON_DELETION])

    def test_non_deletion_marketing_opt_out_requests(self):
        samples = [
            ("Please stop the promotional emails. I still need the account and my order history, so I am not asking for deletion.", RequestType.MARKETING_OPT_OUT),
            ("Please remove me from marketing lists only. I still want receipts and service messages for this account.", RequestType.MARKETING_OPT_OUT),
        ]
        for text, expected_type in samples:
            intent = self.classifier.classify(text)
            self.assertFalse(intent.is_deletion, f"Should NOT be deletion: {text}")
            self.assertEqual(intent.request_type, expected_type)

    def test_login_support_requests(self):
        text = "I can't access my profile and need help resetting the login. Do not close the account."
        intent = self.classifier.classify(text)
        self.assertFalse(intent.is_deletion)

    def test_empty_and_invalid_inputs(self):
        self.assertFalse(self.classifier.is_deletion_authorized(""))
        self.assertFalse(self.classifier.is_deletion_authorized("   "))
        self.assertFalse(self.classifier.is_deletion_authorized(None))
        self.assertFalse(self.classifier.is_deletion_authorized("Hello world, nice weather today!"))


if __name__ == "__main__":
    unittest.main()
