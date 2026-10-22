class CopilotThroughputInfo extends GSInfo {
	function GetAuthor()       { return "CaptainCucumber"; }
	function GetName()         { return "Copilot Throughput Probe"; }
	function GetShortName()    { return "CCTP"; }
	function GetDescription()  { return "Bounded tile-observation and rail-construction throughput fixture for OpenTTD 15.3."; }
	function GetVersion()      { return 1; }
	function GetAPIVersion()   { return "15"; }
	function GetDate()         { return "2026-10-22"; }
	function UseAsRandomAI()   { return false; }
	function IsDeveloperOnly() { return false; }
	function CreateInstance()  { return "CopilotThroughput"; }
}

RegisterGS(CopilotThroughputInfo());
