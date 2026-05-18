import unittest
from unittest.mock import patch, MagicMock
import os

from pkg.agents.chaos.chaos import ChaosAgent

class TestChaosAgent(unittest.TestCase):

    @patch('pkg.agents.chaos.chaos.genai.Client')
    @patch('subprocess.run')
    def test_inject_fault_generate_load(self, mock_run, mock_genai_client):
        # Setup mock run
        mock_run.return_value = MagicMock(stdout="mock stdout", stderr="mock stderr", returncode=0)
        
        # Setup mock GenAI client
        mock_client = MagicMock()
        mock_genai_client.return_value = mock_client
        
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat
        
        # Simulate LLM tool call in the mock
        from pkg.agents.chaos.chaos import _run_command
        
        def fake_send_message(goal):
            cmd = '~/go/bin/fortio load -qps 100 -t 10s -c 2 http://localhost:8080'
            _run_command(cmd)
            
            mock_response = MagicMock()
            mock_response.text = "Disruption complete"
            return mock_response
            
        mock_chat.send_message.side_effect = fake_send_message
        
        agent = ChaosAgent()
        action_spec = {
            "type": "generate_load",
            "target": {
                "service_url": "http://localhost:8082",
                "qps": 100,
                "duration": "10s",
                "concurrency": 2
            }
        }

        # Execute
        agent.inject_fault(action_spec)

        # Verify
        expected_cmd = '~/go/bin/fortio load -qps 100 -t 10s -c 2 http://localhost:8080'
        mock_run.assert_called_once_with(
            expected_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=40
        )

if __name__ == '__main__':
    unittest.main()
