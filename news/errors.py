class Problem(Exception):
    def __init__(
        self,
        message,
        status=422,
        code="invalid_request",
        incident=None,
        *,
        commit=False,
    ):
        super().__init__(message)
        self.status = status
        self.code = code
        self.incident = incident
        self.commit = commit
