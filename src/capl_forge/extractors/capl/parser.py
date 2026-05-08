"""CAPL (.can) script parser — signal/sysvar/envvar extraction.

Extracted from canoe_cfg_inspector.py CfgInspector class.
Battle-tested regex patterns for extracting mappings from CANoe CAPL scripts.
"""
import re
from pathlib import Path


class CaplParser:
    """Parses CAPL (.can) scripts to extract signal/sysvar/envvar mappings."""
    
    # Pattern: on sysvar sysvar::NAMESPACE::VAR_NAME { ... setSignal(SIGNAL, @this); ... }
    SYSVAR_HANDLER = re.compile(
        r'on\s+sysvar(?:_change)?\s+(sysvar::[\w:]+)\s*\{([^}]*)\}',
        re.DOTALL
    )
    
    # Pattern: on envVar VAR_NAME { ... }
    ENVVAR_HANDLER = re.compile(
        r'on\s+envVar\s+(\w+)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
        re.DOTALL
    )
    
    # setSignal(signal_name, value) or setSignal(signal_name, @this)
    SET_SIGNAL = re.compile(r'setSignal\s*\(\s*([\w]+)\s*,\s*([^)]+)\)')
    
    # getSignal(signal_name)
    GET_SIGNAL = re.compile(r'getSignal\s*\(\s*([\w]+)')
    
    # M_MSG.SIGNAL = value (CAN message signal assignment)
    MSG_SIGNAL_ASSIGN = re.compile(r'(M_\w+)\.(\w+)\s*=\s*([^;]+)')
    
    # putvalue/putValue(EV_xxx, value) or putvalue(EV_xxx, value)
    PUT_VALUE = re.compile(r'put[Vv]alue\s*\(\s*(EV_\w+|[\w]+)\s*,\s*([^)]+)\)')
    
    # getvalue/getValue(EV_xxx)
    GET_VALUE = re.compile(r'get[Vv]alue\s*\(\s*(EV_\w+|[\w]+)\s*\)')
    
    # @EV_xxx = value (CAPL shorthand direct envvar write)
    ENVVAR_DIRECT_WRITE = re.compile(r'@(EV_[\w]+)\s*=\s*([^;]+)')
    
    # @EV_xxx in expressions (read, without = after)
    ENVVAR_DIRECT_READ = re.compile(r'@(EV_[\w]+)(?!\s*=)')
    
    # @sysvar:: references in code (both read and write)
    SYSVAR_REF = re.compile(r'@sysvar::([\w:]+)')
    
    # @sysvar::NS::var = value (direct sysvar write)
    SYSVAR_DIRECT_WRITE = re.compile(r'@sysvar::([\w:]+)\s*=\s*([^;]+)')
    
    # testWaitForSignalAvailable/Match/Change patterns
    TEST_SIGNAL_WAIT = re.compile(r'testWaitForSignal\w+\s*\(\s*([\w]+)')
    
    # testcase definitions
    TESTCASE_DEF = re.compile(r'testcase\s+(\w+)')
    
    # message declarations: message 0xID NAME;
    MSG_DECL = re.compile(r'message\s+(0x[0-9A-Fa-f]+)\s+(\w+)\s*;')
    
    def __init__(self):
        self.mappings = []           # sysvar → signal direct mappings
        self.envvar_usages = []      # environment variable usages
        self.sysvar_references = []  # @sysvar:: read references
        self.message_declarations = []
        self.testcases = []          # testcase definitions with their references
        
    def parse(self, filepath):
        """Parse a CAPL .can file."""
        try:
            with open(filepath, 'r', encoding='latin-1') as f:
                content = f.read()
        except Exception as e:
            raise RuntimeError(f"Cannot read CAPL file {filepath}: {e}")
        
        source_file = Path(filepath).name
        
        # 1. Extract on sysvar → setSignal mappings
        self._parse_sysvar_handlers(content, source_file)
        
        # 2. Extract on envVar handlers
        self._parse_envvar_handlers(content, source_file)
        
        # 3. Extract @sysvar:: references
        self._parse_sysvar_references(content, source_file)
        
        # 4. Extract message declarations
        self._parse_message_declarations(content, source_file)
        
        # 5. Extract putvalue/getvalue for environment variables
        self._parse_envvar_usages(content, source_file)
        
        return self.mappings
    
    def _parse_sysvar_handlers(self, content, source_file):
        """Parse 'on sysvar' handlers with setSignal calls AND M_MSG.SIGNAL assignments."""
        pattern = re.compile(
            r'on\s+sysvar(?:_change)?\s+([\w:]+(?:::[\w]+)*)\s*\{',
            re.MULTILINE
        )
        
        for match in pattern.finditer(content):
            # Skip if inside a block comment
            pre = content[max(0, match.start()-200):match.start()]
            if '/*' in pre and '*/' not in pre[pre.rfind('/*'):]:
                continue
            
            sysvar_path = match.group(1).strip()
            # Find the matching closing brace - correctly handles nested braces
            start = match.end()
            brace_count = 1
            pos = start
            while pos < len(content) and brace_count > 0:
                if content[pos] == '{':
                    brace_count += 1
                elif content[pos] == '}':
                    brace_count -= 1
                pos += 1
            
            block = content[start:pos-1]
            
            # Find setSignal calls in this block
            for sig_match in self.SET_SIGNAL.finditer(block):
                signal_name = sig_match.group(1).strip()
                value = sig_match.group(2).strip()
                
                self.mappings.append({
                    'sysvar_path': sysvar_path,
                    'signal_name': signal_name,
                    'mapping_type': 'sysvar_to_signal',
                    'direction': 'write',
                    'value_expr': value,
                    'source_file': source_file,
                    'capl_handler': f'on sysvar {sysvar_path}',
                    'message_name': '',
                    'bus_type': 'LIN'
                })
            
            # Find M_MSG.SIGNAL = value patterns (CAN signal assignments)
            for msg_match in self.MSG_SIGNAL_ASSIGN.finditer(block):
                msg_name = msg_match.group(1).strip()
                signal_name = msg_match.group(2).strip()
                value_expr = msg_match.group(3).strip()
                
                self.mappings.append({
                    'sysvar_path': sysvar_path,
                    'signal_name': signal_name,
                    'mapping_type': 'sysvar_to_can_signal',
                    'direction': 'write',
                    'value_expr': value_expr,
                    'source_file': source_file,
                    'capl_handler': f'on sysvar {sysvar_path}',
                    'message_name': msg_name,
                    'bus_type': 'CAN'
                })
            
            # Find @sysvar::XXX = value patterns (VT-System / direct sysvar writes)
            for sv_match in self.SYSVAR_DIRECT_WRITE.finditer(block):
                sysvar_target = sv_match.group(1).strip()
                value_expr = sv_match.group(2).strip()
                
                self.mappings.append({
                    'sysvar_path': sysvar_path,
                    'signal_name': sysvar_target,
                    'mapping_type': 'sysvar_to_sysvar',
                    'direction': 'write',
                    'value_expr': value_expr,
                    'source_file': source_file,
                    'capl_handler': f'on sysvar {sysvar_path}',
                    'message_name': '',
                    'bus_type': 'VTS' if 'VTS::' in sysvar_target else 'SYSVAR'
                })
    
    def _parse_envvar_handlers(self, content, source_file):
        """Parse 'on envVar' handlers - correctly handles nested braces."""
        pattern = re.compile(r'on\s+envVar\s+(\w+)\s*\{', re.MULTILINE)
        
        for match in pattern.finditer(content):
            # Skip if inside a block comment
            pre = content[max(0, match.start()-200):match.start()]
            if '/*' in pre and '*/' not in pre[pre.rfind('/*'):]:
                continue
            
            envvar_name = match.group(1).strip()
            start = match.end()
            brace_count = 1
            pos = start
            while pos < len(content) and brace_count > 0:
                if content[pos] == '{':
                    brace_count += 1
                elif content[pos] == '}':
                    brace_count -= 1
                pos += 1
            
            block = content[start:pos-1]
            
            # Find setSignal in envvar handler (LIN signals)
            for sig_match in self.SET_SIGNAL.finditer(block):
                self.mappings.append({
                    'sysvar_path': envvar_name,
                    'signal_name': sig_match.group(1).strip(),
                    'mapping_type': 'envvar_to_signal',
                    'direction': 'write',
                    'value_expr': sig_match.group(2).strip(),
                    'source_file': source_file,
                    'capl_handler': f'on envVar {envvar_name}',
                    'message_name': '',
                    'bus_type': 'LIN'
                })
            
            # Find M_MSG.SIGNAL = value patterns (CAN signal assignments)
            for msg_match in self.MSG_SIGNAL_ASSIGN.finditer(block):
                msg_name = msg_match.group(1).strip()
                signal_name = msg_match.group(2).strip()
                value_expr = msg_match.group(3).strip()
                
                self.mappings.append({
                    'sysvar_path': envvar_name,
                    'signal_name': signal_name,
                    'mapping_type': 'envvar_to_can_signal',
                    'direction': 'write',
                    'value_expr': value_expr,
                    'source_file': source_file,
                    'capl_handler': f'on envVar {envvar_name}',
                    'message_name': msg_name,
                    'bus_type': 'CAN'
                })
            
            # Find @sysvar::XXX = value patterns (VT-System / direct sysvar writes)
            for sv_match in self.SYSVAR_DIRECT_WRITE.finditer(block):
                sysvar_target = sv_match.group(1).strip()
                value_expr = sv_match.group(2).strip()
                
                self.mappings.append({
                    'sysvar_path': envvar_name,
                    'signal_name': sysvar_target,
                    'mapping_type': 'envvar_to_sysvar',
                    'direction': 'write',
                    'value_expr': value_expr,
                    'source_file': source_file,
                    'capl_handler': f'on envVar {envvar_name}',
                    'message_name': '',
                    'bus_type': 'VTS' if 'VTS::' in sysvar_target else 'SYSVAR'
                })
            
            # Track the envvar handler itself
            self.envvar_usages.append({
                'name': envvar_name,
                'usage_type': 'handler',
                'source_file': source_file,
                'context': f'on envVar {envvar_name}'
            })
    
    def _parse_sysvar_references(self, content, source_file):
        """Extract @sysvar:: read references."""
        for match in self.SYSVAR_REF.finditer(content):
            ref_path = match.group(1)
            line_start = content.rfind('\n', 0, match.start()) + 1
            line_end = content.find('\n', match.end())
            context_line = content[line_start:line_end].strip()
            
            self.sysvar_references.append({
                'sysvar_path': f"sysvar::{ref_path}",
                'usage_type': 'read',
                'source_file': source_file,
                'context': context_line[:200]
            })
    
    def _parse_message_declarations(self, content, source_file):
        """Extract message declarations."""
        for match in self.MSG_DECL.finditer(content):
            self.message_declarations.append({
                'msg_id': match.group(1),
                'msg_name': match.group(2),
                'source_file': source_file
            })
    
    def _parse_envvar_usages(self, content, source_file):
        """Extract putvalue/getvalue environment variable usages."""
        for match in self.PUT_VALUE.finditer(content):
            self.envvar_usages.append({
                'name': match.group(1),
                'usage_type': 'putvalue',
                'source_file': source_file,
                'context': f'putvalue({match.group(1)}, {match.group(2).strip()})'
            })
        
        for match in self.GET_VALUE.finditer(content):
            self.envvar_usages.append({
                'name': match.group(1),
                'usage_type': 'getvalue',
                'source_file': source_file,
                'context': f'getvalue({match.group(1)})'
            })
        
        # Also capture @EV_xxx = value (direct envvar writes)
        for match in self.ENVVAR_DIRECT_WRITE.finditer(content):
            self.envvar_usages.append({
                'name': match.group(1),
                'usage_type': 'direct_write',
                'source_file': source_file,
                'context': f'@{match.group(1)} = {match.group(2).strip()[:50]}'
            })
        
        # @EV_xxx reads (used in expressions without =)
        for match in self.ENVVAR_DIRECT_READ.finditer(content):
            self.envvar_usages.append({
                'name': match.group(1),
                'usage_type': 'direct_read',
                'source_file': source_file,
                'context': f'@{match.group(1)} (read)'
            })
