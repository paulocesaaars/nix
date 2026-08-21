"""Exceções do Nix. Toda mensagem inclui a ação corretiva."""


class NixError(Exception):
    """Erro de domínio do Nix."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigError(NixError):
    """Configuração inválida, ausente ou incompleta."""


class VaultError(NixError):
    """Falha de leitura, escrita ou varredura do vault."""


class PathEscapeError(VaultError):
    """Tentativa de acessar caminho fora do vault."""


class NoteNotFoundError(VaultError):
    """Nota inexistente no vault."""


class ConfirmationRequiredError(NixError):
    """Operação destrutiva exige confirmação explícita."""


class IndexIncompatibleError(NixError):
    """Índice incompatível com o modelo de embedding configurado."""


class IndexCorruptError(NixError):
    """Índice inconsistente ou schema desatualizado."""


class AttachmentError(NixError):
    """Falha ao extrair texto de um anexo."""
