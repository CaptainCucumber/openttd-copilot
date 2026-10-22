class ForeignEnvironmentInfo extends GSInfo {
	function GetAuthor()       { return "CaptainCucumber"; }
	function GetName()         { return "Foreign Environment Fixture"; }
	function GetShortName()    { return "CCFE"; }
	function GetDescription()  { return "Non-mutating saved-GameScript slot fixture for OpenTTD 15.3."; }
	function GetVersion()      { return 1; }
	function GetAPIVersion()   { return "15"; }
	function GetDate()         { return "2026-10-22"; }
	function UseAsRandomAI()   { return false; }
	function IsDeveloperOnly() { return false; }
	function CreateInstance()  { return "ForeignEnvironment"; }
}

RegisterGS(ForeignEnvironmentInfo());
