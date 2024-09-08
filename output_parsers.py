from typing import Dict
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain.output_parsers import PydanticOutputParser

# Define the expected output model
class RelevantLinksOutput(BaseModel):
    links: Dict[str, str] = Field(description="A dictionary with URLs as keys and 'YES' or 'NO' as values")

# Create the Pydantic output parser using the model
relevant_links_parser = PydanticOutputParser(pydantic_object=RelevantLinksOutput)
