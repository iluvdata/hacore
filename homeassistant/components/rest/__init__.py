"""The rest component."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import (
    SOURCE_IMPORT,
    ConfigEntry,
    ConfigFlowContext,
    ConfigFlowResult,
)
from homeassistant.const import (
    CONF_AUTHENTICATION,
    CONF_HEADERS,
    CONF_METHOD,
    CONF_PARAMS,
    CONF_PASSWORD,
    CONF_PAYLOAD,
    CONF_PLATFORM,
    CONF_RESOURCE,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    HTTP_DIGEST_AUTHENTICATION,
    SERVICE_RELOAD,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import template
from homeassistant.helpers.entity_component import DEFAULT_SCAN_INTERVAL
import homeassistant.helpers.issue_registry as ir
from homeassistant.helpers.reload import async_reload_integration_platforms
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_ENCODING,
    CONF_SSL_CIPHER_LIST,
    CONF_SSL_SECTION,
    DEFAULT_SSL_CIPHER_LIST,
    DOMAIN,
    ENTRY_PLATFORMS,
    PLATFORMS,
)
from .data import RestData
from .schema import CONFIG_SCHEMA as CONFIG_SCHEMA, RESOURCE_SCHEMA

_LOGGER = logging.getLogger(__name__)


@dataclass
class RestRuntimeData:
    """RESTful runtime data."""

    rest: RestData
    coordinator: DataUpdateCoordinator[None]


RestConfigEntry = ConfigEntry[RestRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Migrate the current yaml config to a config entry."""

    if DOMAIN not in config:
        if not [
            entity_config
            for entity_config in config.get(SENSOR_DOMAIN, [])
            if entity_config[CONF_PLATFORM] == DOMAIN
        ] and not [
            entity_config
            for entity_config in config.get(BINARY_SENSOR_DOMAIN, [])
            if entity_config[CONF_PLATFORM] == DOMAIN
        ]:
            return True

    async def reload_service_handler(service: ServiceCall) -> None:
        """Remove all user-defined groups and load new ones from config."""
        _LOGGER.warning(
            "The REST Reload Action only reloads the notify and switch platforms "
            "as the binary_sensor and sensor platforms are configured using the UI "
            "(Config Flow)"
        )
        await async_reload_integration_platforms(hass, DOMAIN, PLATFORMS)

    hass.services.async_register(
        DOMAIN, SERVICE_RELOAD, reload_service_handler, schema=vol.Schema({})
    )

    hass.async_create_task(_async_setup(hass, config))

    return True


async def _async_setup(hass: HomeAssistant, config: ConfigType) -> None:

    async def _import_config(config: ConfigType, config_domain: str) -> bool:
        """Import a RESTful yaml config.

        returns `True` if already imported or successful, `False` on import error.
        """
        for idx, resource in enumerate(config[DOMAIN]):
            result: ConfigFlowResult = await hass.config_entries.flow.async_init(
                DOMAIN,
                context=ConfigFlowContext(
                    source=SOURCE_IMPORT, title_placeholders={"name": f"RESTful {idx}"}
                ),
                data=resource,
            )
            if (
                result.get("type") is FlowResultType.ABORT
                and result.get("reason") != "already_configured"
            ):
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    f"deprecated_yaml_import_issue_{result.get('reason')}",
                    breaks_in_ha_version="2027.8.0",
                    is_fixable=False,
                    issue_domain=DOMAIN,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=f"deprecated_yaml_import_issue_{result.get('reason')}",
                    translation_placeholders={
                        "index": str(idx),
                        "domain": config_domain,
                    },
                )
                return False
        return True

    # Import RESTful config
    if not await _import_config(config[DOMAIN], DOMAIN):
        return

    resource_keys: list[str] = [k.schema for k in RESOURCE_SCHEMA]

    for entity_domain in ENTRY_PLATFORMS:
        for sensor_config in config[entity_domain]:
            if sensor_config.get(CONF_PLATFORM) == DOMAIN:
                new_config: ConfigType = {
                    k: v for k, v in sensor_config.items() if k in resource_keys
                }
                new_config[entity_domain] = [
                    {k: v for k, v in sensor_config.items() if k not in resource_keys}
                ]
                if not await _import_config(new_config, entity_domain):
                    return

    ir.async_create_issue(
        hass,
        DOMAIN,
        "deprecated_yaml",
        breaks_in_ha_version="2026.8.0",
        is_fixable=False,
        issue_domain=DOMAIN,
        severity=ir.IssueSeverity.WARNING,
        translation_key="deprecated_yaml",
    )


async def async_setup_entry(hass: HomeAssistant, config_entry: RestConfigEntry) -> bool:
    """Set up the config entry."""

    rest: RestData = create_rest_data_from_dict(hass, config_entry.data)
    coordinator: DataUpdateCoordinator[None] = _rest_coordinator(
        hass, rest, config_entry
    )

    await coordinator.async_config_entry_first_refresh()

    config_entry.runtime_data = RestRuntimeData(rest, coordinator)

    await hass.config_entries.async_forward_entry_setups(config_entry, ENTRY_PLATFORMS)

    return True


def _rest_coordinator(
    hass: HomeAssistant, rest: RestData, config_entry: RestConfigEntry
) -> DataUpdateCoordinator[None]:
    """Wrap a DataUpdateCoordinator around the rest object.

    Will move to dedicated coordinator class in coordinator.py in future release.
    """
    update_interval: timedelta = config_entry.data.get(
        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
    )
    update_method = rest.async_update

    return DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=config_entry,
        name="rest data",
        update_method=update_method,
        update_interval=update_interval,
    )


async def async_remove_entry(
    hass: HomeAssistant, config_entry: RestConfigEntry
) -> None:
    """Remove a config entry."""


def create_rest_data_from_dict(
    hass: HomeAssistant, data: Mapping[str, Any]
) -> RestData:
    """Create RestData from dict."""

    resource: template.Template = template.Template(data[CONF_RESOURCE], hass)
    method: str = data[CONF_METHOD]
    payload: template.Template | None = data.get(CONF_PAYLOAD)
    verify_ssl: bool = data[CONF_SSL_SECTION][CONF_VERIFY_SSL]
    ssl_cipher_list: str = data[CONF_SSL_SECTION].get(
        CONF_SSL_CIPHER_LIST, DEFAULT_SSL_CIPHER_LIST
    )
    auth: aiohttp.DigestAuthMiddleware | tuple[str, str] | None = None
    if auth_conf := data.get(CONF_AUTHENTICATION):
        username: str | None = auth_conf.get(CONF_USERNAME)
        password: str | None = auth_conf.get(CONF_PASSWORD)
        if username and password:
            if auth_conf.get(CONF_AUTHENTICATION) == HTTP_DIGEST_AUTHENTICATION:
                auth = aiohttp.DigestAuthMiddleware(username, password)
            elif auth_conf.get(
                CONF_AUTHENTICATION
            ):  # check needed as this may be "" which labeled "None" in the selector
                auth = (username, password)
    headers: dict[str, str] | None = data.get(CONF_HEADERS)
    params: dict[str, str] | None = data.get(CONF_PARAMS)
    timeout: int = data[CONF_TIMEOUT]
    encoding: str = data[CONF_ENCODING]

    return RestData(
        hass,
        method,
        resource,
        encoding,
        auth,
        headers,
        params,
        payload,
        verify_ssl,
        ssl_cipher_list,
        timeout,
    )
