import pytest
from .conftest import *


class TestVerifier:
    """Test the TaskNet verifier on valid task networks"""

    def test_tasknet1_1(self):
        """Finds a valid schedule, properties hold"""
        verify_out('tasknet1.tn')(
            "*** NEW SCHEDULE***",
            "heating       : start =   11, end =   80",
            "driving       : start =  100, end =  180",
            "communicating : start =  220, end =  280",
            "PROPERTY 'p1' HOLDS",
            "PROPERTY 'p2' HOLDS",
            "PROPERTY 'p3' HOLDS",
        )

    def test_tasknet2(self):
        """
        Modifiation of tasknet1:
        Loosening start and end ranges, finds different schedule, p2 violated
        """
        verify_out('tasknet2.tn')(
            "heating       : start =    1, end =   29",
            "driving       : start =   30, end =   80",
            "communicating : start =   81, end =  231",
            "PROPERTY 'p1' VIOLATED!",
            "PROPERTY 'p2' VIOLATED!",
            "PROPERTY 'p3' HOLDS"
        )

    def test_tasknet3(self):
        """
        Modification of tasknet2:
        Adds property as a constraint. Now all properties hold again.
        """
        verify_out('tasknet3.tn')(
            "heating       : start =    1, end =   12",
            "driving       : start =   13, end =   63",
            "communicating : start =   64, end =   65",
            "PROPERTY 'p1' VIOLATED!",
            "PROPERTY 'p2' HOLDS",
            "PROPERTY 'p3' HOLDS"
        )

    def test_tasknet4_containedin(self):
        """Simplest possible test."""
        verify_out('tasknet4_containedin.tn')(
            "parent_task   : start =    1, end =    4",
            "child_task    : start =    2, end =    3",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet5_containedin(self):
        """..."""
        verify_out('tasknet5_containedin.tn')(
            "power_session : start =    1, end =    4",
            "sensor_reading: start =    2, end =    3",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet6_simple_optional(self):
        """Test simple optional task that is not included in schedule"""
        verify_out('tasknet6_optional.tn')(
            "*** NEW SCHEDULE***",
            "T1            : start =   50, end =   70",
            "T2            : [OPTIONAL - NOT INCLUDED]",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet7_comprehensive_optional(self):
        """Test comprehensive example with task definitions and optional tasks"""
        verify_out('tasknet7_optional.tn')(
            "*** NEW SCHEDULE***",
            "C1            : start =   36, end =   56",
            "C2            : start =  102, end =  122",
            "C3            : [OPTIONAL - NOT INCLUDED]",
            "C4            : [OPTIONAL - NOT INCLUDED]",
            "PROPERTY 'p1' HOLDS"
        )

    def test_tasknet8_with_definitions_unsat(self):
        """Test overconstrained example with definitions - should be UNSAT"""
        verify_out('tasknet8_defs.tn')(
            "UNSAT",
            "No valid schedule found"
        )

    def test_tasknet9_instances_no_body(self):
        """Testing instances without bodies"""
        verify_out('tasknet9_instances.tn')(
            "T1            : start =   77, end =   97",
            "T2            : start =   74, end =   94",
            "T3            : [OPTIONAL - NOT INCLUDED]",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet10_optimize_mode(self):
        """Test with optional tasks and temporal properties"""
        verify_out('tasknet10_verify.tn')(
            "*** NEW SCHEDULE***",
            "T1            : start =  140, end =  170",
            "T2            : start =  169, end =  199",
            "T3            : [OPTIONAL - NOT INCLUDED]",
            "PROPERTY 'p1' VIOLATED!",
            "Counterexample:",
            "T1            : start =    5, end =    6",
            "T2            : start =    1, end =    4",
            "T3            : start =    3, end =    7"            
        )
    
    def test_tasknet10_satisfy_mode(self):
        """Test with optional tasks and temporal properties"""
        verify_out('tasknet10_verify.tn', mode='satisfy')(
            "*** NEW SCHEDULE***",
            "T1            : start =    5, end =    6",
            "T2            : start =    1, end =    4",
            "T3            : [OPTIONAL - NOT INCLUDED]",
            "PROPERTY 'p1' VIOLATED!",
            "Counterexample:",
            "T1            : start =    1, end =    3",
            "T2            : start =    2, end =    4",
            "T3            : start =    5, end =    6"
        )

    def test_tasknet11_priority(self):
        """Test with priorities and preferred start times"""
        verify_out('tasknet11_priority.tn')(
            "*** NEW SCHEDULE***",
            "T1            : start =   15, end =   25",
            "T2            : [OPTIONAL - NOT INCLUDED]",
            "T3            : [OPTIONAL - NOT INCLUDED]",
            "T4            : start =   75, end =   85",
            "T5            : [OPTIONAL - NOT INCLUDED]",
            "PROPERTY 'p1' HOLDS"
        )

    def test_tasknet12_assign_numeric(self):
        """Test with priorities and preferred start times"""
        verify_out('tasknet12_assign_numeric.tn')(
            "*** NEW SCHEDULE***",
            "heating       : start =    1, end =    2",
            "driving       : start =    3, end =    4",
            "PROPERTY 'p1' HOLDS"
        )
