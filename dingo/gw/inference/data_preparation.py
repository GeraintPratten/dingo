import numpy as np
from gwpy.timeseries import TimeSeries
from astropy.time import Time

from dingo.core.dataset import DingoDataset
from dingo.core.utils import load_data_from_file
from dingo.gw.inference.data_download import download_raw_data
from dingo.gw.gwutils import get_window
from dingo.gw.domains import build_domain_from_model_metadata, FrequencyDomain


def load_raw_data(time_event, settings, event_dataset=None):
    """
    Load raw event data.

    * If event_dataset is provided and event data is saved in it, load and return the data
    * Else, event data is downloaded. If event_dataset is provided, the event data is
      additionally saved to the file.

    Parameters
    ----------
    time_event: float
        gps time of the events
    settings: dict
        dict with the settings
    event_dataset: str
        name of the event dataset file

    Returns
    -------

    """
    event = str(time_event)

    # first try to load the event data from the saved dataset
    if event_dataset is not None:
        data = load_data_from_file(event_dataset, event, settings=settings)
        if data is not None:
            print(f"Data for event at {event} found in {event_dataset}.")
            return data

    # if this did not work, download the data
    print(f"Downloading data for event at {event}.")
    data = download_raw_data(time_event, **settings)

    # optionally save this data to event_dataset
    if event_dataset is not None:
        dataset = DingoDataset(
            dictionary={event: data, "settings": settings}, data_keys=[event]
        )
        print(f"Saving data for event at {event} to {event_dataset}.")
        dataset.to_file(event_dataset, mode="a")

    return data


def parse_settings_for_raw_data(model_metadata, time_psd, time_buffer):
    domain_type = model_metadata["dataset_settings"]["domain"]["type"]

    if domain_type == "FrequencyDomain":
        data_settings = model_metadata["train_settings"]["data"]
        settings = {
            "window": data_settings["window"],
            "detectors": data_settings["detectors"],
            "time_segment": data_settings["window"]["T"],
            "time_psd": time_psd,
            "time_buffer": time_buffer,
            "f_s": data_settings["window"]["f_s"],
        }
    else:
        raise NotImplementedError(f"Unknown domain type {domain_type}")

    return settings


def data_to_domain(raw_data, settings_raw_data, domain, **kwargs):
    """

    Parameters
    ----------
    raw_data
    settings_raw_data
    model_metadata

    Returns
    -------
    data: dict
        dict with domain_data

    """

    if type(domain) == FrequencyDomain:
        window = get_window(kwargs["window"])
        data = {"waveform": {}, "asds": {}}
        # convert event strains to frequency domain
        for det, event_strain in raw_data["strain"].items():
            event_strain = TimeSeries(event_strain, dt=1 / settings_raw_data["f_s"])
            event_strain = event_strain.to_pycbc()
            event_strain = (event_strain * window).to_frequencyseries()
            event_strain = event_strain.cyclic_time_shift(
                settings_raw_data["time_buffer"]
            )
            event_strain = domain.update_data(np.array(event_strain))
            data["waveform"][det] = event_strain

        # convert psds to asds
        for det, psd in raw_data["psd"].items():
            asd = psd ** 0.5
            asd = domain.update_data(asd, low_value=1.0)
            data["asds"][det] = asd

        return data

    else:
        raise NotImplementedError(f"Unknown domain type {type(domain)}")


def get_domain_data(
    model_metadata, time_event, time_psd, time_buffer, event_dataset=None,
):
    # step 1: download raw event data
    settings_raw_data = parse_settings_for_raw_data(
        model_metadata, time_psd, time_buffer
    )
    raw_data = load_raw_data(
        time_event, settings=settings_raw_data, event_dataset=event_dataset
    )

    # step 2: prepare the data for the network domain
    domain_data = data_to_domain(
        raw_data,
        settings_raw_data,
        build_domain_from_model_metadata(model_metadata),
        window=model_metadata["train_settings"]["data"]["window"],
    )

    return domain_data


def get_corrected_sky_position(ra, t_event, t_ref=1126259462.391):
    """
    Calculate the corrected sky position of an event. This is necessary, since the
    model was trained with waveform projections assuming a particular reference time
    t_ref. The corrected sky position takes into account the time difference between
    the event and t_ref.

    Parameters
    ----------
    ra:
        right ascension parameter of the event
    t_event:
        gps time of the event
    t_ref: float
        gps time, used as reference time for the model

    Returns
    -------
    ra_corr: float
        corrected right ascension parameter of the event

    """
    time_reference =  Time(t_ref, format='gps', scale='utc')
    time_event = Time(t_event, format='gps', scale='utc')
    longitude_event = time_event.sidereal_time('apparent', 'greenwich')
    longitude_reference = time_reference.sidereal_time('apparent', 'greenwich')
    delta_longitude = longitude_event - longitude_reference
    ra_correction = delta_longitude.rad
    ra_corr = (ra + ra_correction) % (2 * np.pi)
    return ra_corr