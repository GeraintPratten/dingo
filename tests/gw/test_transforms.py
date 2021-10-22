import pytest
import os.path
import numpy as np
from bilby.gw.detector import InterferometerList

from dingo.gw.transforms_detectors import GetDetectorTimes, ProjectOntoDetectors
from dingo.gw.transforms_parameters import SampleExtrinsicParameters
from dingo.gw.prior_split import default_extrinsic_dict
from dingo.gw.domains import build_domain

@pytest.fixture
def reference_data_research_code():
    dir = os.path.dirname(os.path.realpath(__file__))
    ref_data = np.load(os.path.join(dir, 'waveform_data.npy'),
                       allow_pickle=True).item()
    sample_in = {'parameters': ref_data['intrinsic_parameters'],
                 'waveform': {'h_cross': ref_data['hc'],
                              'h_plus': ref_data['hp']},
                 'extrinsic_parameters': ref_data['extrinsic_parameters']}
    parameters_ref = ref_data['all_parameters']
    h_ref = ref_data['h_d_unwhitened']
    return sample_in, parameters_ref, h_ref

@pytest.fixture
def transforms_setup_1():
    # setup arguments
    extrinsic_prior_dict = default_extrinsic_dict
    ref_time = 1126259462.391
    domain_dict = {'name': 'UniformFrequencyDomain',
                   'kwargs': {'f_min': 10.0, 'f_max': 1024.0, 'delta_f': 0.125,
                              'window_factor': 1.0, 'truncation_range': None}}
    ifo_list = InterferometerList(['H1', 'L1'])
    domain = build_domain(domain_dict)

    # build transformations
    sample_extrinsic_parameters = SampleExtrinsicParameters(extrinsic_prior_dict)
    get_detector_times = GetDetectorTimes(ifo_list, ref_time)
    project_onto_detectors = ProjectOntoDetectors(ifo_list, domain, ref_time)

    return sample_extrinsic_parameters, get_detector_times, \
           project_onto_detectors

def test_detector_projection_agains_research_code(reference_data_research_code,
                                                  transforms_setup_1):
    sample_in, parameters_ref, h_ref = reference_data_research_code
    _, get_detector_times, project_onto_detector = transforms_setup_1

    sample_out = get_detector_times(sample_in)
    sample_out['extrinsic_parameters']['H1_time'] = parameters_ref['H1_time']
    sample_out['extrinsic_parameters']['L1_time'] = parameters_ref['L1_time']
    sample_out = project_onto_detector(sample_out)

    for ifo_name in ['H1', 'L1']:
        strain = sample_out['waveform'][ifo_name]
        strain_ref = h_ref[ifo_name]
        deviation = np.abs(strain_ref - strain)
        assert np.max(deviation) / np.max(np.abs(strain)) < 5e-2

    deviation = np.abs(sample_out['waveform']['H1'] - h_ref['H1'])
