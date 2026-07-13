"""Config Flow for the RESTful integration."""

from datetime import timedelta
from re import search
from typing import Any, override

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import (
    CONF_AUTHENTICATION,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PAYLOAD,
    CONF_RESOURCE,
    CONF_RESOURCE_TEMPLATE,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    Platform,
)
from homeassistant.core import callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.translation import async_get_translations

from . import RestConfigEntry, create_rest_data_from_dict
from .const import (
    CONF_ENCODING,
    CONF_PAYLOAD_TEMPLATE,
    CONF_SSL_CIPHER_LIST,
    CONF_SSL_SECTION,
    DEFAULT_BINARY_SENSOR_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SENSOR_NAME,
    DOMAIN,
    ENTRY_PLATFORMS,
    MIN_SCAN_INTERVAL,
)
from .data import RestData
from .entity import RestEntity
from .schema import (
    BINARY_SENSOR_SUBENTRY_FLOW_SCHEMA,
    OPTIONS_FLOW_SCHEMA,
    RESOURCE_FLOW_SCHEMA,
    RESOURCE_VALIDATION_SCHEMA,
    SENSOR_SUBENTRY_FLOW_SCHEMA,
)
from .util import async_validate_rest_entity

# The follow constants are here to support importing yaml-based config
# and will be removed in a future version of home assistant with the
# exception of _NON_MATCH_KEYS
_OPTIONS_KEYS: list[str] = [CONF_SCAN_INTERVAL]
_NON_MATCH_KEYS: list[str] = [
    CONF_NAME,
    CONF_ENCODING,
    CONF_AUTHENTICATION,
    CONF_TIMEOUT,
    CONF_SSL_SECTION,
    *_OPTIONS_KEYS,
]
_NON_CONFIG_ENTRY_KEYS: list[str] = [*ENTRY_PLATFORMS, *_OPTIONS_KEYS]
_AUTHENTICATION_CONF_KEYS: list[str] = [
    CONF_AUTHENTICATION,
    CONF_USERNAME,
    CONF_PASSWORD,
]
_SSL_CONF_KEYS: list[str] = [CONF_VERIFY_SSL, CONF_SSL_CIPHER_LIST]
_CONF_KEYS_TO_COMBINE: dict[str, str] = {
    CONF_PAYLOAD_TEMPLATE: CONF_PAYLOAD,
    CONF_RESOURCE_TEMPLATE: CONF_RESOURCE,
}
_MIGRATING_KEYS: list[str] = [
    *_CONF_KEYS_TO_COMBINE.keys(),
    *_SSL_CONF_KEYS,
    *_AUTHENTICATION_CONF_KEYS,
]


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
        placeholders: dict[str, Any] = {}
        if user_input is not None:
            self._async_abort_entries_match(
                {
                    key: value
                    for key, value in user_input.items()
                    if key not in _NON_MATCH_KEYS
                }
            )
            try:
                RESOURCE_VALIDATION_SCHEMA(user_input)
                rest: RestData = create_rest_data_from_dict(self.hass, user_input)
                await rest.async_update()
                if rest.last_exception:
                    errors["base"] = "endpoint_error"
                    placeholders = {"error_message": str(rest.last_exception)}
            except vol.Invalid as ex:
                if isinstance(ex, vol.MultipleInvalid):
                    for error in ex.errors:
                        errors[str(error.path[0])] = error.msg
                else:
                    errors["base"] = str(ex)
            if not errors:
                title: str = user_input.pop(CONF_NAME, user_input.get(CONF_RESOURCE))
                if CONF_NAME in user_input:
                    del user_input[CONF_NAME]
                if self.source == SOURCE_RECONFIGURE:
                    return self.async_update_and_abort(
                        self._get_reconfigure_entry(),
                        title=title,
                        data=user_input,
                    )
                return self.async_create_entry(
                    title=title,
                    data=user_input,
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
                )
        return self.async_show_form(
            step_id="user",
            errors=errors,
            description_placeholders=placeholders,
            data_schema=(
                RESOURCE_FLOW_SCHEMA
                if self.source != SOURCE_RECONFIGURE and not user_input
                else (
                    self.add_suggested_values_to_schema(
                        RESOURCE_FLOW_SCHEMA, user_input
                    )
                    if user_input
                    else self.add_suggested_values_to_schema(
                        RESOURCE_FLOW_SCHEMA,
                        {
                            **self._get_reconfigure_entry().data,
                            CONF_NAME: self._get_reconfigure_entry().title,
                        },
                    )
                )
            ),
            last_step=self.source == SOURCE_RECONFIGURE,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any]
    ) -> ConfigFlowResult:
        """Reconfigure the config entry."""
        return await self.async_step_user(None)

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import the data from yaml."""

        # Migrate to the new format to match the config flow entry
        migrated_data: dict[str, Any] = {}
        for key, value in import_data.items():
            if key in _MIGRATING_KEYS:
                if key in [*_SSL_CONF_KEYS, *_AUTHENTICATION_CONF_KEYS]:
                    section: str = (
                        CONF_SSL_SECTION
                        if key in _SSL_CONF_KEYS
                        else CONF_AUTHENTICATION
                    )
                    if section not in migrated_data:
                        migrated_data[section] = {}
                    migrated_data[section][key] = value
                    continue
                if key in _CONF_KEYS_TO_COMBINE:
                    migrated_data[_CONF_KEYS_TO_COMBINE[key]] = value
                    continue
            migrated_data[key] = value

        self._async_abort_entries_match(
            {
                key: value
                for key, value in migrated_data.items()
                if key not in _NON_MATCH_KEYS
            }
        )

        # validate endpoint
        rest: RestData = create_rest_data_from_dict(self.hass, migrated_data)

        await rest.async_update()

        if rest.last_exception is None:
            config_entry_data: dict[str, Any] = {
                k: v for k, v in import_data.items() if k not in _NON_CONFIG_ENTRY_KEYS
            }
            # Store the entity configurations as subentries.
            subentries: list[ConfigSubentryData] = []
            for subentry_type in ENTRY_PLATFORMS:
                if subentry_type in import_data:
                    for idx, subentry_config in enumerate(import_data[subentry_type]):
                        try:
                            entity: RestEntity = async_validate_rest_entity(
                                self.hass, rest, subentry_config, subentry_type
                            )
                            subentries.append(
                                ConfigSubentryData(
                                    data=subentry_config,
                                    title=(
                                        entity.name
                                        if isinstance(entity.name, str)
                                        else (
                                            DEFAULT_BINARY_SENSOR_NAME
                                            if subentry_type is Platform.BINARY_SENSOR
                                            else DEFAULT_SENSOR_NAME
                                        )
                                    ),
                                    subentry_type=subentry_type,
                                    unique_id=f"{subentry_type}_{idx}",
                                )
                            )
                        except (ValueError, TemplateError) as exc:
                            return self.async_abort(
                                reason="render_entity_error",
                                description_placeholders={"message": str(exc)},
                            )
                        finally:
                            self.hass.create_task(entity.async_remove())
            return self.async_create_entry(
                title=self.context["title_placeholders"]["name"],
                data=config_entry_data,
                options={
                    CONF_SCAN_INTERVAL: max(
                        import_data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                        MIN_SCAN_INTERVAL,
                    )
                },
                subentries=subentries,
            )

        if isinstance(rest.last_exception, TimeoutError):
            return self.async_abort(
                reason="timeout",
                description_placeholders={"message": str(rest.last_exception)},
            )
        return self.async_abort(
            reason="client_error",
            description_placeholders={"message": str(rest.last_exception)},
        )

    @staticmethod
    @callback
    @override
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Create the options flow."""
        return RestOptionsFlow()

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            Platform.BINARY_SENSOR: RestSubentryFlow,
            Platform.SENSOR: RestSubentryFlow,
        }


class RestOptionsFlow(OptionsFlow):
    """Options flow for RESTful integration."""

    async def async_step_init(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        """Manage RESTful options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            duration = timedelta(**user_input[CONF_SCAN_INTERVAL]).total_seconds()
            if duration >= MIN_SCAN_INTERVAL:
                return self.async_create_entry(data={CONF_SCAN_INTERVAL: duration})
            errors[CONF_SCAN_INTERVAL] = "min_interval"

        def _duration_dict(seconds: float) -> dict[str, float]:
            mm, ss = divmod(seconds, 60)
            hh, mm = divmod(mm, 60)
            return {"hours": hh, "minutes": mm, "seconds": ss}

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_FLOW_SCHEMA,
                {
                    CONF_SCAN_INTERVAL: _duration_dict(
                        self.config_entry.options[CONF_SCAN_INTERVAL]
                    )
                },
            ),
            description_placeholders={"min_duration": str(MIN_SCAN_INTERVAL)},
            errors=errors,
        )


SUBENTRY_FLOW_FLOW_SCHEMAS = {
    Platform.SENSOR: SENSOR_SUBENTRY_FLOW_SCHEMA,
    Platform.BINARY_SENSOR: BINARY_SENSOR_SUBENTRY_FLOW_SCHEMA,
}


class RestSubentryFlow(ConfigSubentryFlow):
    """Base class for subentry flows."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Base step user."""
        errors: dict[str, Any] = {}
        if user_input is not None:
            config_entry: RestConfigEntry = self._get_entry()
            try:
                # validate the config
                entity: RestEntity = async_validate_rest_entity(
                    self.hass,
                    config_entry.runtime_data.rest,
                    user_input,
                    Platform(self._subentry_type),
                )
            except (ValueError, TemplateError) as exc:
                errors |= {"base": str(exc)}
            finally:
                if entity is not None:
                    config_entry.async_create_background_task(
                        self.hass, entity.async_remove(), name="remove temp rest entity"
                    )
            if not errors:
                title: str = user_input.get(
                    CONF_NAME,
                    (
                        await async_get_translations(
                            self.hass,
                            self.hass.config.language,
                            "title",
                            [self._subentry_type],
                        )
                    ).get(
                        f"component.{self._subentry_type}.title",
                        f"RESTful {self._subentry_type.capitalize}",
                    ),
                )
                if self.source == SOURCE_RECONFIGURE:
                    return self.async_update_reload_and_abort(
                        self._get_entry(),
                        self._get_reconfigure_subentry(),
                        title=title,
                        data=user_input,
                    )
                # generate a unique id
                idx = 0
                for subentry in self._get_entry().subentries.values():
                    if subentry.subentry_type == self._subentry_type:
                        if val := search(r"\d+", subentry.unique_id or "0"):
                            idx = max(int(val.group(0)), idx)
                return self.async_create_entry(
                    title=title,
                    data=user_input,
                    unique_id=f"{self._subentry_type}_{idx + 1}",
                )
        return self.async_show_form(
            step_id="user",
            data_schema=(
                SUBENTRY_FLOW_FLOW_SCHEMAS[Platform(self._subentry_type)]
                if self.source == SOURCE_USER
                else self.add_suggested_values_to_schema(
                    SUBENTRY_FLOW_FLOW_SCHEMAS[Platform(self._subentry_type)],
                    self._get_reconfigure_subentry().data,
                )
            ),
            last_step=True,
        )
