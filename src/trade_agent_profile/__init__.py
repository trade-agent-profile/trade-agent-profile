"""貿易用プロファイル（実験的な参照仕様）のライブラリ。

これは実験的な参照仕様です。いずれの標準化団体の公式仕様でもありません。
"""

from .issues import Issue, ValidationResult
from .messages import new_message, validate_any_file, validate_message
from .profile import (
    MESSAGE_TYPES,
    PROFILE,
    PROFILE_URI,
    PROFILE_VERSION,
    SUPPORTED_PROFILE_VERSIONS,
)
from .rules import find_discrepancies
from .upgrade import UpgradeError, upgrade_shipment
from .validator import (
    LATEST_CONTRACT_VERSION,
    SUPPORTED_CONTRACT_VERSIONS,
    load_schema,
    validate_file,
    validate_shipment,
)

__version__ = "0.1.0"

__all__ = [
    "LATEST_CONTRACT_VERSION",
    "MESSAGE_TYPES",
    "PROFILE",
    "PROFILE_URI",
    "PROFILE_VERSION",
    "SUPPORTED_CONTRACT_VERSIONS",
    "SUPPORTED_PROFILE_VERSIONS",
    "Issue",
    "UpgradeError",
    "ValidationResult",
    "__version__",
    "find_discrepancies",
    "load_schema",
    "new_message",
    "upgrade_shipment",
    "validate_any_file",
    "validate_file",
    "validate_message",
    "validate_shipment",
]
