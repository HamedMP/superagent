import logging

from app.api.workflow_configs.api.api_manager import ApiManager
from app.utils.helpers import (
    MIME_TYPE_TO_EXTENSION,
    get_mimetype_from_url,
    remove_key_if_present,
    rename_and_remove_keys,
)
from app.utils.llm import LLM_REVERSE_MAPPING, get_llm_provider

from .saml_schema import WorkflowDatasource, WorkflowTool

logger = logging.getLogger(__name__)


class DataTransformer:
    def __init__(self, api_user, api_manager: ApiManager):
        self.api_user = api_user
        self.api_manager = api_manager

    @staticmethod
    def transform_tool(tool: WorkflowTool, tool_type: str):
        rename_and_remove_keys(tool, {"use_for": "description"})

        if tool_type:
            tool["type"] = tool_type.upper()

        if tool.get("type") == "FUNCTION":
            tool["metadata"] = {
                "functionName": tool.get("name"),
                **tool.get("metadata", {}),
            }

    @staticmethod
    def transform_assistant(assistant: dict, assistant_type: str):
        remove_key_if_present(assistant, "data")
        remove_key_if_present(assistant, "tools")
        rename_and_remove_keys(
            assistant, {"llm": "llmModel", "intro": "initialMessage"}
        )

        if assistant_type:
            assistant["type"] = assistant_type.upper()

        llm_model = assistant.get("llmModel")

        if assistant.get("type") == "LLM":
            assistant["metadata"] = {
                "model": llm_model,
                **assistant.get("metadata", {}),
            }

        if llm_model:
            provider = get_llm_provider(llm_model)

            if provider:
                assistant["llmProvider"] = provider

            assistant["llmModel"] = LLM_REVERSE_MAPPING.get(llm_model)

        if assistant.get("type") == "LLM":
            remove_key_if_present(assistant, "llmModel")

    async def transform_data(self, data: dict[str, WorkflowDatasource]):
        for datasource_name, datasource in data.items():
            rename_and_remove_keys(datasource, {"use_for": "description"})

            files = []
            for url in datasource.get("urls", []):
                file_type = MIME_TYPE_TO_EXTENSION.get(get_mimetype_from_url(url))

                if file_type:
                    files.append(
                        {
                            "type": file_type,
                            "url": url,
                        }
                    )
                else:
                    logger.warning(
                        f"Could not determine file type for {url}. Skipping..."
                    )

            datasource["files"] = files

            remove_key_if_present(datasource, "urls")

            database_provider = datasource.get("database_provider")

            if database_provider:
                provider = await self.api_manager.get_vector_database_by_provider(
                    database_provider
                )

                # this is for superrag
                if provider:
                    credential_keys_mapping = {
                        # pinecone
                        "PINECONE_API_KEY": "api_key",
                        # qdrant
                        "QDRANT_API_KEY": "api_key",
                        "QDRANT_HOST": "host",
                        # weaviate
                        "WEAVIATE_API_KEY": "api_key",
                        "WEAVIATE_URL": "host",
                    }

                    options = provider.options

                    config = {}
                    if options:
                        for key, value in options.items():
                            new_key = credential_keys_mapping.get(key)
                            if new_key:
                                config[new_key] = value

                    datasource["vector_database"] = {
                        "type": database_provider,
                        "config": config,
                    }

                remove_key_if_present(datasource, "database_provider")

            datasource["index_name"] = datasource_name
