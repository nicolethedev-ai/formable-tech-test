import sys
sys.path.insert(0, '.')
from src.adapters.llm import call_llm

tool = {'name': 'answer', 'description': 'Return the result',
        'inputSchema': {'json': {'type': 'object',
                                 'properties': {'is_abn': {'type': 'boolean'}},
                                 'required': ['is_abn']}}}
print(call_llm('Bạn là bộ kiểm tra.', 'Chuỗi 51824753556 có dạng ABN (11 chữ số) không?',
               tool=tool, step='smoke'))