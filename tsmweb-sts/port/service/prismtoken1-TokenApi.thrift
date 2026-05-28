/**
 * Thrift interface specification for PrismToken
 */

namespace csharp Prism.PrismToken1
namespace netcore Prism.PrismToken1
namespace java za.co.prism.prismtoken1
namespace php Prism.PrismToken1
namespace * PrismPrismToken1


// API version number, use in SessionOptions at sign-in. Server 1.MAX works with client 1.MIN;
// Client 1.X requires server 1.X or higher
const string ApiVersion = "1.1"


// Printable ASCII is a character alphabet defined in STS600-4-2. This const gives the POSIX
// extended regular expression that matches a printable ASCII string (zero or more characters
// in the range x'20 to x'7E (ASCII))
const string PrintableAsciiRe = '^[\\x20-\\x7e]*$' // or '^[[:print:]]*$'


// TTY ASCII is a character alphabet defined for this API; it is printable ASCII plus the LF
// (line feed, ASCII x'10) control character. 


// An IDENT is a type defined in STS600-4-2; this const gives the POSIX extended regular
// expression that matches an IDENT. An IDENT comprises one alphanumeric character (A-Z, a-z, or
// 0-9) followed by 0 to 39 characters that are either alphanumeric or underscore (ASCII x'5F),
// hyphen (ASCII x'2D), period (ASCII x'2E) or comma (ASCII x'2C). An IDENT is a printable ASCII
// string with an overall length of 1 to 40 characters
const string IdentMatchRe = '^[a-zA-Z0-9][a-zA-Z0-9_\\-\\.,]{0,39}$';


// Map of error identifiers (key) to English error descriptions (value). Keys have range IDENT;
// values have range TTY ASCII (printable ASCII plus LF)
const map<string, string> ApiErrors = {
  'EService' : "Unhandled exception '{0}': {1}",
  'EService.Disabled' : "Feature disabled: {0}",
  'EAuthentication.Token' : "Authentication failed (bad accessToken: {0})",
  'EAuthentication.Permission' : "Access denied: accessToken does not have permission '{0}'",
  'EParamRange' : "Parameter '{0}' out of range: got '{1}', expected {2}",
  'ESts.DrnOrPan' : "Parameter '{0}' is an invalid meter DRN/PAN (reason: {2}); got '{1}'",
  'ESts.DrnOrPan.CheckDigit' : "Parameter '{0}' is a meter DRN/PAN with bad check digit(s); got '{1}'",
  'ESignin.Version' : "This service (API version={0}) does not support your client's API version='{1}'",
  'ESignin.Realm' : "Sign-in failed: unknown realm='{0}'",
  'ESignin.Subject' : "Sign-in failed: unknown username='{1}' in realm='{0}'",
  'ESignin.Authentication' : "Sign-in failed: authentication failed for realm='{0}' username='{1}'",
  'ESignin.Permission' : "Sign-in failed: realm='{0}' username='{1}' does not have permission '{2}'", 
  'ESts.IdRecord' : "Parameter '{0}' is an invalid IDRecord/Record2 (reason: {2}); got '{1}'",
  'ESts.IdRecord.Expired' : "Meter identification has expired (YYMM='{0}')",
  'ESm' : "Security Module error '{0}': {1}",
  'EKeystore.NotFound' : "Vending Key not available for SGC={0},KRN={1} (reason: {2})",
  'ECacheMiss' : "The requested entry was not found in the cache",
  'EPrefRange' : "Preference '{0}' out of range: got '{1}', expected {2}",
  'ESts.VkExpired' : "Vending Key has expired (TokenID exceeds KeyExpiryNumber)",
  'ESts.VkBeforeBdt' : "Attempt to use Vending Key before its Base Date",

  // EVerify.* codes are used in VerifyResult.validationResult only  
  'EVerify.Ok' : "(Not an error) Token is valid",
  'EVerify.Crc' : "Invalid token: CRC error", // STS6 API code 3
  'EVerify.DdtkCredit' : "Invalid token: Class 0 token encrypted under a DDTK", // STS6 API code 80
  'EVerify.KeyExpired' : "Invalid token: TokenID out of range for Vending Key KeyExpiryNumber" // STS API code 41
}


// Flags supported by (some) token-issuing methods
enum TokenIssueFlags {
  // The method's tokenTime input is a Unixtime (UTC) to be used as the effective clock. 
  // Mutually exclusive with TID_ADJUST_BDT
  EXTERNAL_CLOCK = 1,
  
  // The method's tokenTime input is a minute offset from BDT=1993 (1993-01-01 00:00 UTC) to use
  // as the TokenID. The value is adjusted to be relative to the VendingKey's BDT, but _is not_
  // adjusted for TokenCancellation or to skip the SpecialReservedTokenIdentifier. Cannot be
  // used with either EXTERNAL_CLOCK or SPECIAL_RESERVED
  TID_ADJUST_BDT = 2,
  
  // Adjust the TokenID to be the SpecialReservedTokenIdentifier (time 00:01) at the start of
  // the day indicated by the system clock (or EXTERNAL_CLOCK). Mutually exclusive with
  // TID_ADJUST_BDT 
  SPECIAL_RESERVED = 4  
}


// Exception class used by all methods in this API. The cause or nature of the exception is
// indicated by the field 'eCode' which allows the client to respond to specific error 
// conditions and to localise the error message
exception ApiException {
  // Identifies the error and its categorisation. Range: IDENT (should be a key from ApiErrors,
  // but clients cannot rely on this as they may be compiled against an older API than the server)
  1: required string eCode,

  // A human-readable message explaining the error, in English. Range: TTY ASCII (printable
  // ASCII plus LF (line break)
  2: required string eMsgEn,
}


// Session options that are common across sign-in methods
struct SessionOptions {
  // Client must set this field to ApiVersion (format is 'VerMajor.VerMinor', where each
  // version part is a decimal integer without leading zeroes)
  1:  required string version = ApiVersion,
  
  // Culture is an IETF language tag [1] per RFC 4646 [2], but we only accept the forms 'LL' or
  // 'LL-CC' where LL is an ISO 639-1 two-letter language code [3] and CC is an ISO 3166-1 
  // alpha-2 (two-letter) country code [4], e.g. 'en' or 'en-ZA'.
  // [1] https://en.wikipedia.org/wiki/IETF_language_tag
  // [2] https://www.ietf.org/rfc/rfc4646.txt
  // [3] https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes
  // [4] https://en.wikipedia.org/wiki/ISO_3166-1
  10: optional string culture = "en"
}


// Result type for all sign-in methods
struct SignInResult {
  // A bearer token that proves the client's authority. Client must treat this value as opaque
  // and keep it secret. Range: printable ASCII
  1: required string accessToken
}


// An identifiable (by a code) error/warning/alert condition that has a description and can be
// localised
struct Alert {
  // Identifies the warning/alert and its categorisation. Range: IDENT (should be a key from
  // ApiErrors, but clients cannot rely on this as they may be compiled against an older API
  // than the server)
  1: required string eCode,

  // A human-readable message explaining the alert, in English. Range: TTY ASCII (printable
  // ASCII plus LF (line break)
  2: required string eMsgEn,
}


// Status of a node in a tree network of PrismToken instances (method getStatus() returns a list of these)
struct NodeStatus {
  // Associative array of status information. Keys have range IDENT, values are printable ASCII
  1: required map<string, string> info,

  // Zero or more alert messages
  2: required list<Alert> alerts
}


// Carries the new meter configuration (to be established by the PrismToken issuing a KCT) when a
// change has been captured on the Vending System
struct MeterConfigAmendment {
  // New SupplyGroupCode, range 0-999999
  1: required i32 toSgc,
  // New KeyRevisionNumber, range 1-9
  2: required i16 toKrn,
  // New TariffIndex, range 0-99
  3: required i16 toTi
}


// Identifies the meter configurtion in token-issuing calls
struct MeterConfigIn {
  // Meter invariants
  
    // DecoderReferenceNumber; 11- or 13-digit DRN, or 18-digit PAN (with IIN 600727 or 0000 
    // only), with valid Luhn(s)
    1: required string drn,
    // EncryptionAlgorithm, range 0-99; only 7,11 currently supported
    2: required i16 ea,
    // TokenCarrierType, range 0-99
    3: required i16 tct,
  
  // Active configuration (SGC & KRN together identify the VK)
  
    // SupplyGroupCode, range 0-999999
    10: required i32 sgc,
    // KeyRevisionNumber, range 1-9
    11: required i16 krn,
    // TariffIndex, range 0-99
    12: required i16 ti,
    
  // Intended configuration
  
    // If present then issue a Key Change Token Set from the active configuration to the
    // intended configuration before issuing the token (using the new configuration).
    // If allowKrnUpdate is true then the latest effective KRN for the SGC is used instead
    // of newConfig.toKrn. A token-issuing call will issue at most one KCT Set, combining the
    // effects from multiple KCT triggers (newConfig, allowKrnUpdate, allowKenUpdate)
    20: optional MeterConfigAmendment newConfig,
    
    // Issue KCT when newer KRN is available for SGC. If true and the meter's KRN (given by krn,
    // or by newConfig.toKrn if present) is not the latest effective KRN for the SGC, then issue
    // a Key Change Token Set to update the KRN (see also comment for newConfig)
    21: optional bool allowKrnUpdate = true,   
  
  // Meter state & options per Vending System
  
    // KeyExpiryNumber, range 0-255
    30: required i16 ken,
    
    // Date of expiry (of the meter card). Range 4 digits giving 'YYMM', omit or '0000' if unused
    31: optional string doe = '0000',
    
    // (Only for EA=07) Use 3-token set when issuing key change tokens
    32: optional bool allow3Kct = false,
    
    // Issue KCT when meter KEN differs from VK KEN. If true and the meter's KEN (given by ken)
    // does not match the Vending Key's key (for the VK identified by sgc & krn), then issue a
    // Key Change Token set to update the KEN (see also comment for newConfig)
    33: optional bool allowKenUpdate = true
}


// Carries the new meter configuration to be stored by the Vending System as a consequence of
// a Key Change Token Set being issued to the meter 
struct MeterConfigAdvice {
  // New configuration

    // New SupplyGroupCode, range 0-999999
    1: required i32 toSgc,
    // New KeyRevisionNumber, range 1-9
    2: required i16 toKrn,
    // New TariffIndex, range 0-99
    3: required i16 toTi,
    // New KeyExpiryNumber, range 0-255
    4: required i16 toKen,

  // Meter card representation of new configuration
  
    // IEC 62055-41 IDRecord (is printable ASCII)
    10: required string idRecord,
    // IEC 62055-51 Record2 (with ETX/STX without LRC) (is printable ASCII)
    11: required string record2,

  // Additional information
  
    // The value of the Rollover (RO) bit in the Key Change Token set
    20: required bool rollover
    // Key Check Value (KCV) of the new Vending Key (from which the DecoderKey contained in this KCT set was derived) as 6 ASCII hexadecimal digits: 0-9 A-F
    21: required string toVkKcv
  
}


// A single STS token (and associated metadata) returned by token-issuing methods (that produce
// encrypted class=0 or class=2 tokens)
struct Token {
  // Meter configuration
    // DecoderReferenceNumber; 11- or 13-digit DRN, with valid Luhn
    1: required string drn,
    // Meter PrimaryAccountNumber; 18-digit PAN, with valid Luhns
    2: required string pan,
    // EncryptionAlgorithm, range 0-99
    3: required i16 ea,
    // TokenCarrierType, range 0-99
    4: required i16 tct,
    // SupplyGroupCode, range 0-999999
    5: required i32 sgc,
    // KeyRevisionNumber, range 1-9
    6: required i16 krn,
    // TariffIndex, range 0-99
    7: required i16 ti,

  // Token fields
    // Token Class, range 0-3
    10: required i16 tokenClass,
    // Token SubClass, range 0-15
    11: required i16 subclass,
    // TokenIdentifier (TID), range 0-16777215
    12: required i32 tid,
    // TransferAmount (uncompressed); see IEC 623055-41 for range. Value is the actual units
    // represented by the token, which may be rounded (in the customer's favour) from requested
    // amount
    13: required double transferAmount,
    
    // True if tid is a SpecialReservedTokenIdentifier
    14: required bool isReservedTid,
    // New meter configuration resulting from a Key Change; field is set if-and-only-if this is
    // the 1st token in a KCT set
    15: optional MeterConfigAdvice newConfig, 

  // Token interpretation
    // Human-readable description of the token's purpose (English, printable ASCII). The purpose
    // is determined by the tokenClass and subclass
    20: required string description,
    // Human-readable unit name for transferAmount (English, printable ASCII, short)
    21: required string stsUnitName,
    // transferAmount scaled to a user-friendly unit and formatted for printing (printable ASCII)
    22: required string scaledAmount,
    // Human-readable unit name for scaledAmount (English, printable ASCII, short)
    23: required string scaledUnitName,
  
  // Token
    // The token as 20 ASCII decimal digits (0-9), for printing or meter card Record1
    30: required string tokenDec,
    // The token as 17 ASCII hexadecimal digits: 0-9 A-F 
    31: required string tokenHex,
    
  // SM identification
    // STS600-4-2 ID_SM (PKID with rectype SMID) (is printable ASCII)
    40: required string idSm,
    // Key Check Value (KCV) of the Vending Key that encryted this token, as 6 ASCII hexadecimal digits: 0-9 A-F
    41: required string vkKcv
}


// A single STS class=1 test token (and associated metadata)
struct MeterTestToken {
  // Meter this token was issued for (or a reserved DRN for generic test tokens)
    // DecoderReferenceNumber; 11- or 13-digit DRN, with valid Luhn
    1: required string drn,
    // Meter PrimaryAccountNumber; 18-digit PAN, with valid Luhns
    2: required string pan,

  // Token fields
    // Token Class, will be 1  
    10: required i16 tokenClass,
    // Token SubClass, range 0-15
    11: required i16 subclass,
    // InitiateMeterTest/DisplayControlField; 28 bits integer for subclass 1,6-10; 36-bit
    // integer for subclass 0,11-15. See See [IEC 62055-41] section 6.2.3 and Table 22 
    12: required i64 control,
    // ManufacturerCode; ranges 0 for subclasses 0,1; 100-9999 for 6-10; 0-99 for 11-15.
    // See [IEC 62055-41] section 6.2.3    
    13: required i16 mfrcode,
    
  // Token interpretation
    // Human-readable description of the token's purpose (English, printable ASCII). The purpose
    // is determined by the tokenClass and subclass
    20: required string description,    

  // Token
    // The token as 20 ASCII decimal digits (0-9), for printing or meter card Record1
    30: required string tokenDec,
    // The token as 17 ASCII hexadecimal digits: 0-9 A-F 
    31: required string tokenHex
}


// Result returned by method verifyToken
struct VerifyResult {
  // Result of validation: 'EVerify.Ok' if the token is valid (and exactly one of the optional
  // fields will be present), else an 'EVerify.*' error code from ApiErrors
  1: required string validationResult,
  // Describes the token when the input was a valid class=0 or class=2 (except KCT) token
  2: optional Token token,
  // Describes the token when the input was a valid class=1 token
  3: optional MeterTestToken meterTestToken
}


service TokenApi {

  // Tests connectivity between a Thrift client and server. The server delays for 'sleepMs'
  // milliseconds then returns the 'echo' string.  
  string ping(
    // Milliseconds to delay before responding; range 0 - 60000
    1: required i32 sleepMs,
    // String to echo back to the client; Unicode, length 0 to 65535 characters
    2: required string echo
  ) throws (
    1: ApiException ex1
  ),


  // Signs in with a username and password, to obtain an access token
  SignInResult signInWithPassword(
    // Used to log system-wide context; range IDENT
    1: required string messageId,
    // Authentication realm; range IDENT. Use 'local' to check the username and password against the PrismToken local user database.
    2: required string realm,
    // Username within the realm; realm & username together identify the subject; range IDENT
    3: required string username,
    // Cleartext password for the user; range printable ASCII, maximum length 55
    4: required string password,
    // Options for this session 
    5: required SessionOptions sessionOpts
  ) throws (
    1: ApiException ex1
  ),
  
  
  // Retrieves the status of the PrismToken instance (or a tree of PrismToken instances behind a
  // facade). Each NodeStatus in the output list (min length 1) represents the status of one
  // PrismToken in the tree; the list is ordered as a pre-order depth-first traversal of the tree
  list<NodeStatus> getStatus(
    // Used to log system-wide context; range IDENT
    1: required string messageId,
    // Bearer token proving authority of the caller; as obtained from a sign-in method
    2: required string accessToken
  ) throws (
    1: ApiException ex1
  ),
  
  
  // Parses an IEC 62055-41 IDRecord or IEC 62055-41 Record2 (from a meter card), and returns
  // a MeterConfigIn giving the meter configuration indicated by the record
  MeterConfigIn parseIdRecord(
    // Used to log system-wide context; range IDENT
    1: required string messageId,
    // Bearer token proving authority of the caller; as obtained from a sign-in method
    2: required string accessToken,
    // IEC 62055-41 IDRecord, or IEC 62055-51 Record2 (STX, ETX optional; no LRC) (is printable ASCII)
    3: required string idRecord
  ) throws (
    1: ApiException ex1
  ),


  // Uploads the supplied license to the SM such that a non-expired, valid license causes the SM's
  // transaction counter to be set to a non-zero value thereby enabling token vending
  // Returns true on success or throws an exception
  bool loadTransactionLicense(
    // Used to log system-wide context; range IDENT
    1: required string messageId,
    // Bearer token proving authority of the caller; as obtained from a sign-in method
    2: required string accessToken
    // String containing the transaction license (including START/END guards);
    // license may be embedded in other text (e.g. an e-mail message)
    3: required string licenseText
  ) throws (
    1: ApiException ex1
  ),


  // Issues an STS credit (class=0) token. The result contains one or more tokens, with at least
  // one credit token; other tokens may include automatically generated Key Change tokens 
  list<Token> issueCreditToken(
    // Used to log system-wide context, and for fetchTokenResult; range IDENT
    1: required string messageId,
    // Bearer token proving authority of the caller; as obtained from a sign-in method
    2: required string accessToken,
    // Meter that is intended to consume this token 
    3: required MeterConfigIn meterConfig,
    // Credit token SubClass; range 0-15
    4: required i16 subclass,
    // Quantity of STS transfer units (not encoded/compressed); range for subclass 0-3: integer
    // 0-18201624; for subclass 4-7: -1.6383e30 - 1.6383e30, to 5 decimal places (0.00001)
    5: required double transferAmount,
    // Effective time of vend; range depends on flags, see TokenIssueFlags
    6: required i64 tokenTime,
    // Transaction options; bitmap of TokenIssueFlags
    7: required i64 flags
  ) throws (
    1: ApiException ex1
  ),
  
   
  // Issues an STS InitMeterTest (class=1) token (also known as "Non-meter-specific engineering"
  // or "NMSE")
  MeterTestToken issueMeterTestToken(
    // Used to log system-wide context; range IDENT
    1: required string messageId,
    // Bearer token proving authority of the caller; as obtained from a sign-in method
    2: required string accessToken,
    // Token SubClass; range 0-15; 2-5 RFU
    3: required i16 subclass,
    // InitiateMeterTest/DisplayControlField; 28 bits integer for subclass 1,6-10; 36-bit
    // integer for subclass 0,11-15. See [IEC 62055-41] section 6.2.3 and Table 22
    4: required i64 control,
    // ManufacturerCode; ranges 0 for subclasses 0,1; 100-9999 for 6-10; 0-99 for 11-15.
    // See See [IEC 62055-41] section 6.2.3
    5: required i16 mfrcode,
  ) throws (
    1: ApiException ex1
  ),

  
  // Issues an STS management (class=2) token (also known as "Meter-specific engineering" or 
  // "MSE"). The result contains one or more tokens, with at least one MSE token; other tokens
  // may include automatically generated Key Change tokens
  list<Token> issueMseToken(
    // Used to log system-wide context, and for fetchTokenResult; range IDENT
    1: required string messageId,
    // Bearer token proving authority of the caller; as obtained from a sign-in method
    2: required string accessToken,
    // Meter that is intended to consume this token 
    3: required MeterConfigIn meterConfig,
    // MSE token SubClass; range 0-15
    4: required i16 subclass,
    // Quantity of STS transfer units (not encoded/compressed); range depends on subclass - see
    // IEC 62055-41
    5: required double transferAmount,
    // Effective time of vend; range depends on flags, see TokenIssueFlags
    6: required i64 tokenTime,
    // Transaction options; bitmap of TokenIssueFlags
    7: required i64 flags
  ) throws (
    1: ApiException ex1
  ),


  // Issues an STS Key Change Token Set. The result contains the KCT Set which will comprise two
  // or more tokens.
  list<Token> issueKeyChangeTokens(
    // Used to log system-wide context, and for fetchTokenResult; range IDENT
    1: required string messageId,
    // Bearer token proving authority of the caller; as obtained from a sign-in method
    2: required string accessToken,
    // Meter that is intended to consume this token (current configuration).
    // meterConfig.newConfig is ignored (method parameter newConfig is used instead), but 
    // meterConfig.allowKrnUpdate=1 may override toKrn in parameter newConfig 
    3: required MeterConfigIn meterConfig,
    // Intended meter configuration after key change. This overrides meterConfig.newConfig,
    // but the toKrn field may be affected by meterConfig.allowKrnUpdate 
    4: required MeterConfigAmendment newConfig 
  ) throws (
    1: ApiException ex1
  ),


  // Verifies a previously-issued STS token, returning a verification result (indicates whether
  // the token is valid, or the verification error) and (for a valid token) details of the
  // token's parameters/contents. This method cannot verify a Meter Test Token (class=1), or a 
  // DITK Change Token.
  VerifyResult verifyToken(
    // Used to log system-wide context; range IDENT
    1: required string messageId,
    // Bearer token proving authority of the caller; as obtained from a sign-in method
    2: required string accessToken,
    // Meter that is intended to consume this token 
    3: required MeterConfigIn meterConfig,
    // The token as 20 ASCII decimal digits (0-9)
    4: required string tokenDec
  ) throws (
    1: ApiException ex1
  ),
  

  // Issues a Key Change Token Set from a Decoder Initialization Transfer Key (DITK, also known
  // as a Decoder ROM Key) to a Default (VDDK), Unique (VUDK) or Common (VCDK) type Vending Key.
  // This method is only supported if the SM has Manufacturing firmware.
  list<Token> issueDitkChangeTokens(
    // Used to log system-wide context, and for fetchTokenResult; range IDENT
    1: required string messageId,
    // Bearer token proving authority of the caller; as obtained from a sign-in method
    2: required string accessToken,
    // Meter that is intended to consume this token (meterConfig.newConfig is ignored) 
    3: required MeterConfigIn meterConfig,
  ) throws (
    1: ApiException ex1
  ),


  // Fetches the result of a recent call to a token-issuring method. If a client fails to
  // receive the result of an RPC call, it should use this method to discover the result (if
  // any) or to confirm that PrismToken did not receive the transaction. Simply re-trying a call
  // to a method that issues encrypted tokens will affect the meter's TokenCancellation list and
  // the risk-control counters in the SM.
  list<Token> fetchTokenResult(
    // Used to log system-wide context; range IDENT
    1: required string messageId,
    // Bearer token proving authority of the caller; as obtained from a sign-in method
    2: required string accessToken,
    // Identifies the messageId of the transaction/result to fetch; range IDENT
    3: required string reqMessageId
  ) throws (
    1: ApiException ex1
  ),


  // (For CTS testing mode only) Zeroises the TokenCancellation lists of zero or more meters.
  // Returns a list of affected DRNs.
  list<string> ctsResetTidList(
    // Used to log system-wide context; range IDENT
    1: required string messageId,
    // Bearer token proving authority of the caller; as obtained from a sign-in method
    2: required string accessToken,
    // Wildcard match against PANs in PrismToken's database (wildcards: ? and *); range 1-18 digits
    // with optional wildcards (*, ?)
    3: required string panPattern
  ) throws (
    1: ApiException ex1
  )

}
