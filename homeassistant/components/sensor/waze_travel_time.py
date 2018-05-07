"""
Support for Waze travel time sensor.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.waze_travel_time/
"""
from datetime import timedelta
import logging

import requests
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import ATTR_ATTRIBUTION, CONF_NAME, CONF_REGION, ATTR_LATITUDE, ATTR_LONGITUDE
import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.location as location
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

REQUIREMENTS = ['WazeRouteCalculator==0.5']

_LOGGER = logging.getLogger(__name__)

ATTR_DISTANCE = 'distance'
ATTR_ROUTE = 'route'

CONF_ATTRIBUTION = "Data provided by the Waze.com"
CONF_DESTINATION = 'destination'
CONF_ORIGIN = 'origin'

DEFAULT_NAME = 'Waze Travel Time'

ICON = 'mdi:car'

REGIONS = ['US', 'NA', 'EU', 'IL']

SCAN_INTERVAL = timedelta(minutes=5)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_ORIGIN): cv.string,
    vol.Required(CONF_DESTINATION): cv.string,
    vol.Required(CONF_REGION): vol.In(REGIONS),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
})

TRACKABLE_DOMAINS = ['device_tracker', 'sensor', 'zone']

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Waze travel time sensor platform."""
    destination = config.get(CONF_DESTINATION)
    name = config.get(CONF_NAME)
    origin = config.get(CONF_ORIGIN)
    region = config.get(CONF_REGION)

    try:
        waze_data = WazeRouteData(hass, origin, destination, region)
    except requests.exceptions.HTTPError as error:
        _LOGGER.error("%s", error)
        return

    add_devices([WazeTravelTime(waze_data, name)], True)


class WazeTravelTime(Entity):
    """Representation of a Waze travel time sensor."""

    def __init__(self, waze_data, name):
        """Initialize the Waze travel time sensor."""
        self._name = name
        self._state = None
        self.waze_data = waze_data

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return round(self._state['duration'])

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return 'min'

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return ICON

    @property
    def device_state_attributes(self):
        """Return the state attributes of the last update."""
        return {
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION,
            ATTR_DISTANCE: round(self._state['distance']),
            ATTR_ROUTE: self._state['route'],
        }

    def update(self):
        """Fetch new state data for the sensor."""
        try:
            self.waze_data.update()
            self._state = self.waze_data.data
        except KeyError:
            _LOGGER.error("Error retrieving data from server")


class WazeRouteData(object):
    """Get data from Waze."""

    def __init__(self, hass, origin, destination, region):
        """Initialize the data object."""
        # Check if location is a trackable entity
        if origin.split('.', 1)[0] in TRACKABLE_DOMAINS:
            self._origin_entity_id = origin
        else:
            self._origin = origin

        if destination.split('.', 1)[0] in TRACKABLE_DOMAINS:
            self._destination_entity_id = destination
        else:
            self._destination = destination

        self._hass = hass
        self._region = region
        self.data = {}

    @Throttle(SCAN_INTERVAL)
    def update(self):
        """Fetch latest data from Waze."""
        import WazeRouteCalculator
        _LOGGER.debug("Update in progress...")
        try:

            # Convert device_trackers to google friendly location
            if hasattr(self, '_origin_entity_id'):
                self._origin = self._get_location_from_entity(
                    self._origin_entity_id
                )

            if hasattr(self, '_destination_entity_id'):
                self._destination = self._get_location_from_entity(
                    self._destination_entity_id
                )

            self._destination = self._resolve_zone(self._destination)
            self._origin = self._resolve_zone(self._origin)

            params = WazeRouteCalculator.WazeRouteCalculator(
                self._origin, self._destination, self._region, None)
            results = params.calc_all_routes_info()
            best_route = next(iter(results))
            (duration, distance) = results[best_route]
            best_route_str = bytes(best_route, 'ISO-8859-1').decode('UTF-8')
            self.data['duration'] = duration
            self.data['distance'] = distance
            self.data['route'] = best_route_str
        except WazeRouteCalculator.WRCError as exp:
            _LOGGER.error("Error on retrieving data: %s", exp)
            return
    def _get_location_from_entity(self, entity_id):
        """Get the location from the entity state or attributes."""
        entity = self._hass.states.get(entity_id)

        if entity is None:
            _LOGGER.error("Unable to find entity %s", entity_id)
            self.valid_api_connection = False
            return None

        # Check if the entity has location attributes
        if location.has_location(entity):
            return self._get_location_from_attributes(entity)

        # Check if device is in a zone
        zone_entity = self._hass.states.get("zone.%s" % entity.state)
        if location.has_location(zone_entity):
            _LOGGER.debug(
                "%s is in %s, getting zone location",
                entity_id, zone_entity.entity_id
            )
            return self._get_location_from_attributes(zone_entity)

        # If zone was not found in state then use the state as the location
        if entity_id.startswith("sensor."):
            return entity.state

        # When everything fails just return nothing
        return None

    @staticmethod
    def _get_location_from_attributes(entity):
        """Get the lat/long string from an entities attributes."""
        attr = entity.attributes
        return "%s,%s" % (attr.get(ATTR_LATITUDE), attr.get(ATTR_LONGITUDE))

    def _resolve_zone(self, friendly_name):
        entities = self._hass.states.all()
        for entity in entities:
            if entity.domain == 'zone' and entity.name == friendly_name:
                return self._get_location_from_attributes(entity)

        return friendly_name
