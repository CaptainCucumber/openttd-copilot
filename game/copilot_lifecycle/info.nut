class CopilotLifecycleInfo extends GSInfo {
	function GetAuthor()       { return "CaptainCucumber"; }
	function GetName()         { return "Copilot Lifecycle Probe"; }
	function GetShortName()    { return "CCLC"; }
	function GetDescription()  { return "Versioned Admin and save/reload lifecycle fixture for OpenTTD 15.3."; }
	function GetVersion()      { return 1; }
	function GetAPIVersion()   { return "15"; }
	function GetDate()         { return "2026-10-21"; }
	function UseAsRandomAI()   { return false; }
	function IsDeveloperOnly() { return false; }
	function CreateInstance()  { return "CopilotLifecycle"; }
}

RegisterGS(CopilotLifecycleInfo());
