class CopilotProbeInfo extends GSInfo {
	function GetAuthor()      { return "CaptainCucumber"; }
	function GetName()        { return "Copilot Control Probe"; }
	function GetShortName()   { return "CCPB"; }
	function GetDescription() { return "Bounded human-company control and accounting probe for OpenTTD 15.3."; }
	function GetVersion()     { return 1; }
	function GetAPIVersion()  { return "15"; }
	function GetDate()        { return "2026-10-21"; }
	function UseAsRandomAI()  { return false; }
	function IsDeveloperOnly(){ return false; }
	function CreateInstance() { return "CopilotProbe"; }
}

RegisterGS(CopilotProbeInfo());
