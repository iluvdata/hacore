"""Config Flow for the RESTful integration."""

from typing import Any, override

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_AUTHENTICATION, CONF_RESOURCE, CONF_USERNAME
from homeassistant.helpers.template import Template

from . import create_rest_data_from_config_entry
from .const import DOMAIN
from .schema import RESOURCE_FLOW_SCHEMA


class RestConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for the RESTful integration."""

    VERSION = 1
    MINOR_VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step in config flow."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            rest = create_rest_data_from_config_entry(self.hass, user_input)
            await rest.async_update()
            if rest.last_exception:
                errors["base"] = "endpoint_error"
                placeholders["error_message"] = str(rest.last_exception)
            if not errors:
                title: str = Template(
                    user_input[CONF_RESOURCE], self.hass
                ).async_render()
                if self.source == SOURCE_USER:
                    return self.async_create_entry(title=title, data=user_input)
                return self.async_update_and_abort(
                    self._get_reconfigure_entry(),
                    title=title,
                    data=user_input,
                )
        suggested_values = user_input or (
            self._get_reconfigure_entry().data
            if self.source == SOURCE_RECONFIGURE
            else {}
        )
        return self.async_show_form(
            step_id="user",
            errors=errors,
            description_placeholders=placeholders,
            data_schema=(
                self.add_suggested_values_to_schema(
                    data_schema=RESOURCE_FLOW_SCHEMA(
                        CONF_AUTHENTICATION not in suggested_values
                        or CONF_USERNAME not in suggested_values[CONF_AUTHENTICATION]
                    ),
                    suggested_values=suggested_values,
                )
            ),
            last_step=True,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure the config entry."""
        return await self.async_step_user(user_input)
