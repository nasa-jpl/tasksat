import pytest
from .conftest import *


class TestVerifier:
    """Test the TaskNet verifier on valid task networks"""

    def test_tasknet1_1(self):
        """Finds a valid schedule, properties hold"""
        verify_out('tasknet1.tn')(
            "*** NEW SCHEDULE***",
            "heating       : start =    1, end =   81",
            "driving       : start =  100, end =  180",
            "communicating : start =  200, end =  280",
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
            "heating       : start =",
            "driving       : start =",
            "communicating : start =",
            "PROPERTY 'p1' HOLDS",
            "PROPERTY 'p2' VIOLATED!",
            "PROPERTY 'p3' HOLDS"
        )

    def test_tasknet3(self):
        """
        Modification of tasknet2:
        Adds property as a constraint. Now all properties hold again.
        """
        verify_out('tasknet3.tn')(
            "heating       : start =    1, end =   81",
            "driving       : start =   82, end =  162",
            "communicating : start =  163, end =  243",
            "PROPERTY 'p1' HOLDS",
            "PROPERTY 'p2' HOLDS",
            "PROPERTY 'p3' HOLDS"
        )

    def test_tasknet4_containedin(self):
        """Simplest possible test."""
        verify_out('tasknet4_containedin.tn')(
            "parent_task   : start =    2, end =  102",
            "child_task    : start =    3, end =   43",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet5_containedin(self):
        """..."""
        verify_out('tasknet5_containedin.tn')(
            "power_session : start =    2, end =  102",
            "sensor_reading: start =    3, end =   43",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet6_simple_optional(self):
        """Test simple optional task that is not included in schedule"""
        verify_out('tasknet6_optional.tn')(
            "*** NEW SCHEDULE***",
            "T1            : start =",
            "T2            : [OPTIONAL - NOT INCLUDED]",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet7_comprehensive_optional(self):
        """Test comprehensive example with task definitions and optional tasks"""
        verify_out('tasknet7_optional.tn')(
            "*** NEW SCHEDULE***",
            "C1            : start =",
            "C2            : start =",
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
            "T1            : start =   79, end =   99",
            "T2            : start =   26, end =   46",
            "T3            : [OPTIONAL - NOT INCLUDED]",
            "No temporal properties attached to this TaskNet."
        )

    def test_tasknet10_verify_mode(self):
        """Test verify mode - finds any valid schedule (not necessarily optimal)"""
        verify_out('tasknet10_verify.tn')(
            "*** NEW SCHEDULE***",
            "T1            : start =   57, end =   87",
            "T2            : start =   26, end =   56",
            "T3            : [OPTIONAL - NOT INCLUDED]",
            "PROPERTY 'p1' VIOLATED!"
        )
    
        