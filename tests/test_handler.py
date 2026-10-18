from src.handler import lambda_handler


def test_lambda_scaffold_is_explicitly_unimplemented():
    result = lambda_handler({}, None)
    assert result["status"] == "NOT_IMPLEMENTED"
