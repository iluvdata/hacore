"""Support for RESTful API sensors."""

from collections.abc import Mapping
import logging
from typing import Any, override
from xml.parsers.expat import ExpatError

from jsonpath import ExprSyntaxError, JSONPathTypeError, search

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import (
    CONF_FORCE_UPDATE,
    CONF_RESOURCE_TEMPLATE,
    CONF_VALUE_TEMPLATE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.trigger_template_entity import (
    ManualTriggerSensorEntity,
    ValueTemplate,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.json import json_loads

from . import RestConfigEntry
from .const import CONF_JSON_ATTRS, CONF_JSON_ATTRS_PATH, DEFAULT_SENSOR_NAME
from .data import RestData
from .entity import RestEntity, async_get_trigger_entity_config

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RestConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup the RESTful binary sensors."""

    for subentry_id, subentry in config_entry.subentries.items():
        if subentry.subentry_type == SENSOR_DOMAIN:
            async_add_entities(
                [
                    RestSensor(
                        hass,
                        config_entry.runtime_data.coordinator,
                        config_entry.runtime_data.rest,
                        subentry.data,
                    )
                ],
                config_subentry_id=subentry_id,
            )


class RestSensor(ManualTriggerSensorEntity, RestEntity):
    """Implementation of a REST sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator[None] | None,
        rest: RestData,
        config: Mapping[str, Any],
    ) -> None:
        """Initialize the REST sensor."""
        ManualTriggerSensorEntity.__init__(
            self,
            hass,
            async_get_trigger_entity_config(hass, rest, config, DEFAULT_SENSOR_NAME),
        )
        RestEntity.__init__(
            self,
            coordinator,
            rest,
            config.get(CONF_RESOURCE_TEMPLATE),
            config[CONF_FORCE_UPDATE],
        )
        self._value_template: ValueTemplate | None = config.get(CONF_VALUE_TEMPLATE)
        self._json_attrs = config.get(CONF_JSON_ATTRS)
        self._json_attrs_path = config.get(CONF_JSON_ATTRS_PATH)
        self._attr_extra_state_attributes = {}

    @property
    @override
    def available(self) -> bool:
        """Return if entity is available."""
        available1 = RestEntity.available.fget(self)  # type: ignore[attr-defined]
        available2 = ManualTriggerSensorEntity.available.fget(self)  # type: ignore[attr-defined]
        return bool(available1 and available2)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return dict(self._attr_extra_state_attributes)

    @override
    def update_from_rest_data(self) -> None:
        """Update state from the rest data."""
        try:
            value = self.rest.data_without_xml()
        except ExpatError as err:
            _LOGGER.warning(
                "REST xml result could not be parsed and converted to JSON: %s", err
            )
            value = self.rest.data

        variables = self._template_variables_with_value(value)
        if not self._render_availability_template(variables):
            self.async_write_ha_state()
            return

        if self._json_attrs:
            self._attr_extra_state_attributes = _parse_json_attributes(
                value, self._json_attrs, self._json_attrs_path
            )

        if value is not None and self._value_template is not None:
            value = self._value_template.async_render_as_value_template(
                self.entity_id, variables, None
            )

        self._set_native_value_with_possible_timestamp(value)
        self._process_manual_data(variables)
        self.async_write_ha_state()


def _parse_json_attributes(
    value: str | None, json_attrs: list[str], json_attrs_path: str | None
) -> dict[str, Any]:
    """Parse JSON attributes."""
    if not value:
        _LOGGER.warning("Empty reply found when expecting JSON data")
        return {}

    try:
        json_dict = json_loads(value)
        if json_attrs_path is not None:
            json_dict = search(json_attrs_path, json_dict)
        if isinstance(json_dict, list) and json_dict:
            json_dict = json_dict[0]
        if isinstance(json_dict, dict):
            return {k: json_dict[k] for k in json_attrs if k in json_dict}

        _LOGGER.warning(
            "JSON result was not a dictionary or list with 0th element a dictionary"
        )
    except ValueError, TypeError, ExprSyntaxError, JSONPathTypeError:
        _LOGGER.warning("REST result could not be parsed as JSON")
        _LOGGER.debug("Erroneous JSON: %s", value)

    return {}
