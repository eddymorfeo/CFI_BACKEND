from pydantic import BaseModel


class ExportCartolaBancariaResponse(BaseModel):
    message: str
    file_name: str
    file_path: str
    rows_exported: int