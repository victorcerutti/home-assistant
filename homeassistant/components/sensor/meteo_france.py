"""
Support for Meteo France raining forecast.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.meteofrance/
"""
import datetime
import ftplib
import gzip
import io
import json
import logging
import os
import re
import zipfile

import requests
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_NAME)
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
import homeassistant.helpers.config_validation as cv

_RESOURCE = 'http://www.meteofrance.com/mf3-rpc-portlet/rest/pluie/{}/'
_LOGGER = logging.getLogger(__name__)

CONF_ATTRIBUTION = "Data provided by the Meteo France"
CONF_LOCATION_ID = '12345'

MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(minutes=5)

# Sensor types are defined like: Name, units
SENSOR_TYPES = {
    'rain_forecast': ['Rain forecast', None]
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_LOCATION_ID): cv.string,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the BOM sensor."""
    location = config.get(CONF_LOCATION_ID)
#    if location is None:
        #todo

    MeteoFrance_data = MeteoFranceCurrentData(hass, location)

    _LOGGER.error("Received info from MeteoFrance_Current: %s", MeteoFrance_data)

    try:
        MeteoFrance_data.update()
    except ValueError as err:
        _LOGGER.error("Received error from MeteoFrance_Current: %s", err)
        return False
    add_device(MeteoFranceCurrentSensor(MeteoFrance_data, 'rain_forecast', config.get(CONF_NAME)))
    return True


class MeteoFranceCurrentSensor(Entity):
    """Implementation of a Meteo France current sensor."""

    def __init__(self, MeteoFrance_data, condition, location):
        """Initialize the sensor."""
        self.MeteoFrance_data = MeteoFrance_data
        self._condition = condition
        self.stationname = stationname

    @property
    def name(self):
        """Return the name of the sensor."""
        if self.stationname is None:
            return 'BOM {}'.format(SENSOR_TYPES[self._condition][0])

        return 'BOM {} {}'.format(
            self.stationname, SENSOR_TYPES[self._condition][0])

    @property
    def state(self):
        """Return the state of the sensor."""
        if self.bom_data.data and self._condition in self.bom_data.data:
            return self.bom_data.data[self._condition]

        return STATE_UNKNOWN

    @property
    def device_state_attributes(self):
        """Return the state attributes of the device."""
        attr = {}
        attr['Sensor Id'] = self._condition
        attr['Zone Id'] = self.bom_data.data['history_product']
        attr['Station Id'] = self.bom_data.data['wmo']
        attr['Station Name'] = self.bom_data.data['name']
        attr['Last Update'] = datetime.datetime.strptime(str(
            self.bom_data.data['local_date_time_full']), '%Y%m%d%H%M%S')
        attr[ATTR_ATTRIBUTION] = CONF_ATTRIBUTION
        return attr

    @property
    def unit_of_measurement(self):
        """Return the units of measurement."""
        return SENSOR_TYPES[self._condition][1]

    def update(self):
        """Update current conditions."""
        self.bom_data.update()


class MeteoFranceCurrentData(object):
    """Get data from Meteo France."""

    def __init__(self, hass, location_id):
        """Initialize the data object."""
        self._hass = hass
        self._location_id = location_id
        self.data = None

    def _build_url(self):
        url = _RESOURCE.format(self._location_id)
        _LOGGER.info("Meteo France URL %s", url)
        return url

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Get the latest data from Meteo France."""
        try:
            result = requests.get(self._build_url(), timeout=10).json()
            self.data = result#['observations']['data'][0]
        except ValueError as err:
            _LOGGER.error("Check Meteo France %s", err.args)
            self.data = None
            raise
