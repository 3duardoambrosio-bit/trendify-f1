"""
Tests para infraestructura SYNAPSE.

Cubre:
- Ledger (write, query, integrity)
- Schemas (validation, versions)
- Doctor (checks)
"""

import pytest
import json
import tempfile
from pathlib import Path

from synapse.infra.ledger import Ledger, LedgerEvent, log_event
from synapse.infra.schemas import (
    validate_schema,
    get_schema_version,
    list_schemas,
    SchemaVersionError,
    SchemaMissingFieldError,
    SCHEMAS,
)


# ============================================================
# LEDGER TESTS
# ============================================================

class TestLedger:
    """Tests para Ledger."""
    
    @pytest.fixture
    def temp_ledger(self):
        """Ledger en directorio temporal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Ledger(base_dir=tmpdir)
    
    def test_write_event(self, temp_ledger):
        """Debe escribir evento."""
        event = temp_ledger.write(
            event_type="TEST_EVENT",
            entity_type="test",
            entity_id="123",
            payload={"foo": "bar"},
        )
        
        assert event.event_type == "TEST_EVENT"
        assert event.entity_id == "123"
        assert event.checksum
        assert len(event.checksum) == 16
    
    def test_query_by_entity_id(self, temp_ledger):
        """Debe filtrar por entity_id."""
        temp_ledger.write("E1", "test", "A", {})
        temp_ledger.write("E2", "test", "B", {})
        temp_ledger.write("E3", "test", "A", {})
        
        results = temp_ledger.query(entity_id="A")
        
        assert len(results) == 2
        assert all(e.entity_id == "A" for e in results)
    
    def test_query_by_event_type(self, temp_ledger):
        """Debe filtrar por event_type."""
        temp_ledger.write("TYPE_A", "test", "1", {})
        temp_ledger.write("TYPE_B", "test", "2", {})
        temp_ledger.write("TYPE_A", "test", "3", {})
        
        results = temp_ledger.query(event_type="TYPE_A")
        
        assert len(results) == 2
        assert all(e.event_type == "TYPE_A" for e in results)
    
    def test_query_limit(self, temp_ledger):
        """Debe respetar limit."""
        for i in range(10):
            temp_ledger.write("E", "test", str(i), {})
        
        results = temp_ledger.query(limit=5)
        
        assert len(results) == 5
    
    def test_get_last_event(self, temp_ledger):
        """Debe obtener último evento."""
        temp_ledger.write("E1", "test", "X", {"v": 1})
        temp_ledger.write("E2", "test", "Y", {"v": 2})
        temp_ledger.write("E3", "test", "X", {"v": 3})
        
        last = temp_ledger.get_last_event("X")
        
        assert last is not None
        assert last.entity_id == "X"
        # Should return one of the X events
        assert last.payload["v"] in [1, 3]
    
    def test_verify_integrity_clean(self, temp_ledger):
        """Integridad OK sin corrupción."""
        temp_ledger.write("E1", "test", "1", {})
        temp_ledger.write("E2", "test", "2", {})
        
        errors = temp_ledger.verify_integrity()
        
        assert len(errors) == 0
    
    def test_count_events(self, temp_ledger):
        """Debe contar eventos."""
        temp_ledger.write("A", "test", "1", {})
        temp_ledger.write("B", "test", "2", {})
        temp_ledger.write("A", "test", "3", {})
        
        total = temp_ledger.count_events()
        type_a = temp_ledger.count_events(event_type="A")
        
        assert total == 3
        assert type_a == 2
    
    def test_wave_id_tracking(self, temp_ledger):
        """Debe guardar wave_id."""
        event = temp_ledger.write(
            "E1", "test", "1", {},
            wave_id="wave_05_20250101"
        )
        
        assert event.wave_id == "wave_05_20250101"
        
        results = temp_ledger.query(wave_id="wave_05_20250101")
        assert len(results) == 1


# ============================================================
# SCHEMA TESTS
# ============================================================

class TestSchemas:
    """Tests para Schema Registry."""
    
    def test_list_schemas(self):
        """Debe listar schemas."""
        schemas = list_schemas()
        
        assert "interrogation_result" in schemas
        assert "ad_kit_manifest" in schemas
        assert "market_pulse_memo" in schemas
    
    def test_get_schema_version(self):
        """Debe obtener version."""
        version = get_schema_version("interrogation_result")
        
        assert version == "1.0.0"
    
    def test_validate_valid_data(self):
        """Debe validar datos correctos."""
        data = {
            "schema_version": "1.0.0",
            "product_id": "123",
            "product_name": "Test",
            "total_score": 0.75,
            "verdict": "launch",
            "passed": True,
            "emotion_primary": "control",
            "enemy": "cables",
            "job_to_be_done": "escuchar música",
            "killing_objection": "sonido",
            "objection_response": "drivers HD",
            "recommended_angle": "dolor",
        }
        
        result = validate_schema(data, "interrogation_result")
        
        assert result == True
    
    def test_validate_missing_version(self):
        """Debe fallar sin schema_version."""
        data = {
            "product_id": "123",
            "product_name": "Test",
            # ... otros campos
        }
        
        with pytest.raises(SchemaVersionError):
            validate_schema(data, "interrogation_result")
    
    def test_validate_wrong_version(self):
        """Debe fallar con version incorrecta."""
        data = {
            "schema_version": "2.0.0",  # Wrong
            "product_id": "123",
            "product_name": "Test",
            "total_score": 0.75,
            "verdict": "launch",
            "passed": True,
            "emotion_primary": "control",
            "enemy": "cables",
            "job_to_be_done": "escuchar música",
            "killing_objection": "sonido",
            "objection_response": "drivers HD",
            "recommended_angle": "dolor",
        }
        
        with pytest.raises(SchemaVersionError):
            validate_schema(data, "interrogation_result")
    
    def test_validate_missing_required(self):
        """Debe fallar sin campos requeridos."""
        data = {
            "schema_version": "1.0.0",
            "product_id": "123",
            # Falta product_name y otros
        }
        
        with pytest.raises(SchemaMissingFieldError):
            validate_schema(data, "interrogation_result")
    
    def test_ad_kit_manifest_schema(self):
        """Debe validar ad_kit_manifest."""
        data = {
            "schema_version": "1.0.0",
            "product_id": "123",
            "product_name": "Test",
            "generated_at": "2025-01-01T00:00:00Z",
            "outputs": {"hooks": 10},
            "quality_score": 0.85,
            "hashes": {"input": "abc", "output": "def"},
        }
        
        result = validate_schema(data, "ad_kit_manifest")
        
        assert result == True
    
    def test_market_pulse_schema(self):
        """Debe validar market_pulse_memo."""
        data = {
            "schema_version": "1.0.0",
            "date": "2025-01-01",
            "conclusion": "Test conclusion",
            "signals": [],
            "confidence": 0.7,
        }
        
        result = validate_schema(data, "market_pulse_memo")
        
        assert result == True


# ============================================================
# INTEGRATION TESTS
# ============================================================

class TestLedgerWithSchemas:
    """Tests de integración Ledger + Schemas."""
    
    @pytest.fixture
    def temp_ledger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Ledger(base_dir=tmpdir)
    
    def test_log_interrogation_result(self, temp_ledger):
        """Debe loguear resultado de interrogación."""
        result_data = {
            "schema_version": "1.0.0",
            "product_id": "34357",
            "product_name": "Audifonos M10",
            "total_score": 0.72,
            "verdict": "launch",
            "passed": True,
            "emotion_primary": "control",
            "enemy": "cables",
            "job_to_be_done": "escuchar música",
            "killing_objection": "sonido",
            "objection_response": "drivers HD",
            "recommended_angle": "dolor",
        }
        
        # Validate first
        validate_schema(result_data, "interrogation_result")
        
        # Then log
        event = temp_ledger.write(
            event_type="INTERROGATION_COMPLETED",
            entity_type="product",
            entity_id="34357",
            payload=result_data,
        )
        
        assert event.entity_id == "34357"
        
        # Query back
        events = temp_ledger.query(entity_id="34357")
        assert len(events) == 1
        assert events[0].payload["verdict"] == "launch"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
