from pathlib import Path

import pytest
from pydantic import ValidationError

from rutile3.data.catalog import checksum
from rutile3.data.precipitation import select_parameters
from rutile3.domain.microstructure import AgingConditions, Microstructure, PrecipitationParameters


def test_bundled_preset_applies_only_to_matching_sources_and_condition():
    source = Path("data/matcalc/ni")
    assessment = checksum((source / "mc_ni_v2036.tdb").read_bytes())
    mobility = checksum((source / "mc_ni_v2012.ddb").read_bytes())
    matrix = {"phase": "FCC_A1", "composition": {"AL": .125, "NI": .875}}
    aging = AgingConditions(temperature_k=823.15, duration_s=3600, pressure_pa=101325)
    override = PrecipitationParameters(source="Example user input", precipitates=[
        {"phase": "GAMMA_PRIME", "interfacial_energy_j_m2": .023},
    ])
    parameters, preset = select_parameters(assessment, mobility, matrix, aging, override)
    assert preset["id"] == "matcalc-ni-gamma-prime-823k"
    assert parameters.precipitates[0].interfacial_energy_j_m2 == .023
    assert parameters.precipitates[0].molar_volume_m3_mol_atoms > 0
    other_temperature = aging.model_copy(update={"temperature_k": 850})
    with pytest.raises(ValueError, match="No precipitation preset"):
        select_parameters(assessment, mobility, matrix, other_temperature, None)
    with pytest.raises(ValueError, match="GAMMA_PRIME molar volume"):
        select_parameters(assessment, "different", matrix, aging, override)


def test_microstructure_exchange_preserves_missing_values_and_checks_sample_order():
    row = {"time_s": 10, "temperature_k": 823, "precipitates": [{"phase": "GAMMA_PRIME", "volume_fraction": 0}]}
    record = {"origin": "measured", "source": "Example measurements", "matrix_phase": "FCC_A1", "samples": [row]}
    imported = Microstructure.model_validate(record)
    assert imported.samples[0].precipitates[0].volume_fraction == 0
    assert imported.samples[0].precipitates[0].number_density_m3 is None
    with pytest.raises(ValidationError, match="sample times must increase"):
        Microstructure.model_validate({**record, "samples": [row, row]})
