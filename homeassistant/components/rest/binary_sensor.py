"""Support for RESTful binary sensors."""

from collections.abc import Mapping
import logging
from typing import Any, override
from xml.parsers.expat import ExpatError

from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_FORCE_UPDATE,
    CONF_RESOURCE_TEMPLATE,
    CONF_VALUE_TEMPLATE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.trigger_template_entity import (
    ManualTriggerEntity,
    ValueTemplate,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_BINARY_SENSOR_NAME
from .data import RestData
from .entity import RestEntity, async_get_trigger_entity_config

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup the RESTful binary sensors."""

    for subentry_id, subentry in config_entry.subentries.items():
        if subentry.subentry_type == BINARY_SENSOR_DOMAIN:
            async_add_entities(
                [
                    RestBinarySensor(
                        hass,
                        config_entry.runtime_data.coordinator,
                        config_entry.runtime_data.rest,
                        subentry.data,
                    )
                ],
                config_subentry_id=subentry_id,
            )


class RestBinarySensor(ManualTriggerEntity, RestEntity, BinarySensorEntity):
    """Representation of a REST binary sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator[None] | None,
        rest: RestData,
        config: Mapping[str, Any],
    ) -> None:
        """Initialize a REST binary sensor."""
        ManualTriggerEntity.__init__(
            self,
            hass,
            async_get_trigger_entity_config(
                hass, rest, config, DEFAULT_BINARY_SENSOR_NAME
            ),
        )
        RestEntity.__init__(
            self,
            coordinator,
            rest,
            config.get(CONF_RESOURCE_TEMPLATE),
            config[CONF_FORCE_UPDATE],
        )
        self._previous_data = None
        self._value_template: ValueTemplate | None = config.get(CONF_VALUE_TEMPLATE)

    @property
    @override
    def available(self) -> bool:
        """Return if entity is available."""
        available1 = RestEntity.available.fget(self)  # type: ignore[attr-defined]
        available2 = ManualTriggerEntity.available.fget(self)  # type: ignore[attr-defined]
        return bool(available1 and available2)

    @override
    def update_from_rest_data(self) -> None:
        """Update state from the rest data."""
        if self.rest.data is None:
            self._attr_is_on = False
            return

        try:
            response = self.rest.data_without_xml()
        except ExpatError as err:
            self._attr_is_on = False
            _LOGGER.warning(
                "REST xml result could not be parsed and converted to JSON: %s", err
            )
            return

        variables = self._template_variables_with_value(response)
        if not self._render_availability_template(variables):
            self.async_write_ha_state()
            return

        if response is not None and self._value_template is not None:
            response = self._value_template.async_render_as_value_template(
                self.entity_id, variables, False
            )

        try:
            self._attr_is_on = bool(int(str(response)))
        except ValueError:
            self._attr_is_on = {
                "true": True,
                "on": True,
                "open": True,
                "yes": True,
            }.get(str(response).lower(), False)

        self._process_manual_data(variables)
        self.async_write_ha_state()
