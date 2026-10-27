"""例外の定義。CollectError のメッセージはそのまま通知に載せるので、利用者が読める日本語で書く。"""


class ConfigError(Exception):
    """config.yaml の不備。全体の処理を止める。"""


class CollectError(Exception):
    """地域単位の収集失敗。その地域だけ失敗扱いにして、他の地域は続ける。"""


class FetchError(CollectError):
    pass


class ExtractionError(CollectError):
    pass


class VersionError(CollectError):
    pass


class ValidationError(CollectError):
    pass


class ArchiveError(CollectError):
    pass


class StorageError(CollectError):
    pass
