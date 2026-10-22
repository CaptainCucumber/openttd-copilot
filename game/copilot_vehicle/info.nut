class CopilotVehicleInfo extends GSInfo {
	function GetAuthor()       { return "CaptainCucumber"; }
	function GetName()         { return "Copilot Vehicle Probe"; }
	function GetShortName()    { return "CCVP"; }
	function GetDescription()  { return "Bounded vehicle, orders, and coal-delivery fixture for OpenTTD 15.3."; }
	function GetVersion()      { return 1; }
	function GetAPIVersion()   { return "15"; }
	function GetDate()         { return "2026-10-22"; }
	function UseAsRandomAI()   { return false; }
	function IsDeveloperOnly() { return false; }
	function CreateInstance()  { return "CopilotVehicle"; }
}

RegisterGS(CopilotVehicleInfo());
