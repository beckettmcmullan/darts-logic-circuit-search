module photon_core (clk,
    rst,
    valid,
    arrival,
    candidate);
 input clk;
 input rst;
 input valid;
 input [9:0] arrival;
 output [9:0] candidate;

 wire _000_;
 wire _001_;
 wire _002_;
 wire _003_;
 wire _004_;
 wire _005_;
 wire _006_;
 wire _007_;
 wire _008_;
 wire _009_;
 wire _010_;
 wire _011_;
 wire _012_;
 wire _013_;
 wire _014_;
 wire _015_;
 wire _016_;
 wire _017_;
 wire _018_;
 wire _019_;
 wire _020_;
 wire _021_;
 wire _022_;
 wire _023_;
 wire _024_;
 wire _025_;
 wire _026_;
 wire _027_;
 wire _028_;
 wire _029_;
 wire _030_;
 wire _031_;
 wire _032_;
 wire _033_;
 wire _034_;
 wire _035_;
 wire _036_;
 wire _037_;
 wire _038_;
 wire _039_;
 wire _040_;
 wire _041_;
 wire _042_;
 wire _043_;
 wire _044_;
 wire _045_;
 wire _046_;
 wire _047_;
 wire _048_;
 wire _049_;
 wire _050_;
 wire _051_;
 wire _052_;
 wire _053_;
 wire _054_;
 wire _055_;
 wire _056_;
 wire _057_;
 wire _058_;
 wire _059_;
 wire _060_;
 wire _061_;
 wire _062_;
 wire _063_;
 wire _064_;
 wire _065_;
 wire _066_;
 wire _067_;
 wire _068_;
 wire _069_;
 wire _070_;
 wire _071_;
 wire _072_;
 wire _073_;
 wire _074_;
 wire _075_;
 wire _076_;
 wire _077_;
 wire _078_;
 wire _079_;
 wire _080_;
 wire _081_;
 wire _082_;
 wire _083_;
 wire _084_;
 wire _085_;
 wire _086_;
 wire _087_;
 wire _088_;
 wire _089_;
 wire _090_;
 wire _091_;
 wire _092_;
 wire _093_;
 wire _094_;
 wire _095_;
 wire _096_;
 wire _097_;
 wire _098_;
 wire _099_;
 wire _100_;
 wire _101_;
 wire _102_;
 wire _103_;
 wire _104_;
 wire _105_;
 wire _106_;
 wire _107_;
 wire _108_;
 wire _109_;
 wire _110_;
 wire _111_;
 wire _112_;
 wire _113_;
 wire _114_;
 wire _115_;
 wire _116_;
 wire _117_;
 wire _118_;
 wire _119_;
 wire _120_;
 wire _121_;
 wire _122_;
 wire _123_;
 wire _124_;
 wire _126_;
 wire _127_;
 wire _128_;
 wire _129_;
 wire _130_;
 wire _131_;
 wire _132_;
 wire _133_;
 wire _135_;
 wire _136_;
 wire _137_;
 wire _138_;
 wire _139_;
 wire _140_;
 wire _141_;
 wire _142_;
 wire _143_;
 wire _144_;
 wire _145_;
 wire _146_;
 wire _147_;
 wire _148_;
 wire _149_;
 wire _151_;
 wire _152_;
 wire _153_;
 wire _154_;
 wire _155_;
 wire _156_;
 wire _157_;
 wire _158_;
 wire _159_;
 wire _160_;
 wire _161_;
 wire _162_;
 wire _163_;
 wire _164_;
 wire _165_;
 wire _166_;
 wire _167_;
 wire _168_;
 wire _169_;
 wire _170_;
 wire _171_;
 wire _172_;
 wire _173_;
 wire _174_;
 wire _175_;
 wire _176_;
 wire _177_;
 wire _178_;
 wire _179_;
 wire _180_;
 wire _181_;
 wire _182_;
 wire _183_;
 wire _184_;
 wire _185_;
 wire _186_;
 wire _187_;
 wire _188_;
 wire _189_;
 wire _190_;
 wire _191_;
 wire _192_;
 wire _193_;
 wire _194_;
 wire _195_;
 wire _196_;
 wire _197_;
 wire _198_;
 wire _199_;
 wire _200_;
 wire _201_;
 wire _202_;
 wire _203_;
 wire _204_;
 wire _205_;
 wire _206_;
 wire _207_;
 wire _208_;
 wire _209_;
 wire _210_;
 wire _211_;
 wire _212_;
 wire _213_;
 wire _214_;
 wire _215_;
 wire _216_;
 wire _217_;
 wire _218_;
 wire _219_;
 wire _220_;
 wire _221_;
 wire _222_;
 wire _223_;
 wire _224_;
 wire _225_;
 wire _226_;
 wire _227_;
 wire _228_;
 wire _229_;
 wire _230_;
 wire _231_;
 wire _232_;
 wire _233_;
 wire _234_;
 wire _235_;
 wire _236_;
 wire _237_;
 wire _238_;
 wire _239_;
 wire _240_;
 wire _241_;
 wire _243_;
 wire _244_;
 wire _245_;
 wire _246_;
 wire _247_;
 wire _248_;
 wire _249_;
 wire _250_;
 wire _251_;
 wire _253_;
 wire _255_;
 wire _256_;
 wire _258_;
 wire _259_;
 wire _260_;
 wire _261_;
 wire _263_;
 wire _264_;
 wire _265_;
 wire _266_;
 wire _267_;
 wire _268_;
 wire _269_;
 wire _270_;
 wire _271_;
 wire _272_;
 wire _273_;
 wire _274_;
 wire _275_;
 wire _276_;
 wire _277_;
 wire _278_;
 wire _279_;
 wire _280_;
 wire _281_;
 wire _282_;
 wire _283_;
 wire _284_;
 wire _285_;
 wire _286_;
 wire _287_;
 wire _288_;
 wire _289_;
 wire _290_;
 wire _291_;
 wire _292_;
 wire _293_;
 wire _294_;
 wire _295_;
 wire _296_;
 wire _297_;
 wire _298_;
 wire _299_;
 wire _300_;
 wire _301_;
 wire _302_;
 wire _303_;
 wire _304_;
 wire _305_;
 wire _306_;
 wire _307_;
 wire _308_;
 wire _310_;
 wire _311_;
 wire _312_;
 wire _313_;
 wire _314_;
 wire _315_;
 wire _316_;
 wire _317_;
 wire _318_;
 wire _319_;
 wire _320_;
 wire _321_;
 wire _322_;
 wire _323_;
 wire _324_;
 wire _325_;
 wire _326_;
 wire _327_;
 wire _328_;
 wire _329_;
 wire _330_;
 wire _331_;
 wire _332_;
 wire _333_;
 wire _334_;
 wire _335_;
 wire _336_;
 wire _337_;
 wire _338_;
 wire _339_;
 wire _340_;
 wire _341_;
 wire _342_;
 wire _343_;
 wire _344_;
 wire _345_;
 wire _346_;
 wire _347_;
 wire _348_;
 wire _349_;
 wire _350_;
 wire _351_;
 wire _352_;
 wire _353_;
 wire _354_;
 wire _355_;
 wire _356_;
 wire _357_;
 wire _358_;
 wire _359_;
 wire _360_;
 wire _361_;
 wire _362_;
 wire _363_;
 wire _364_;
 wire _365_;
 wire _366_;
 wire _367_;
 wire _368_;
 wire _369_;
 wire _370_;
 wire _371_;
 wire _372_;
 wire _373_;
 wire _374_;
 wire _375_;
 wire _376_;
 wire _377_;
 wire _378_;
 wire _379_;
 wire _380_;
 wire \above[0] ;
 wire \above[1] ;
 wire net1;
 wire net2;
 wire net3;
 wire net4;
 wire net5;
 wire net6;
 wire net7;
 wire net8;
 wire net9;
 wire net10;
 wire \below[0] ;
 wire \below[1] ;
 wire net13;
 wire net14;
 wire net15;
 wire net16;
 wire net17;
 wire net18;
 wire net19;
 wire net20;
 wire net21;
 wire net22;
 wire \confidence[0] ;
 wire \confidence[1] ;
 wire \confidence[2] ;
 wire do_down;
 wire do_inc;
 wire g0_15;
 wire g0_8;
 wire g1_11;
 wire g1_15;
 wire g1_3;
 wire near16;
 wire net11;
 wire \stepped[0] ;
 wire net12;
 wire clknet_0_clk;
 wire clknet_1_0__leaf_clk;
 wire clknet_1_1__leaf_clk;

 INVx1_ASAP7_75t_R _381_ (.A(_041_),
    .Y(net22));
 INVx1_ASAP7_75t_R _382_ (.A(\stepped[0] ),
    .Y(net13));
 INVx1_ASAP7_75t_R _383_ (.A(_009_),
    .Y(net14));
 INVx1_ASAP7_75t_R _384_ (.A(_082_),
    .Y(net15));
 INVx1_ASAP7_75t_R _385_ (.A(_044_),
    .Y(net16));
 INVx1_ASAP7_75t_R _386_ (.A(_034_),
    .Y(net17));
 INVx1_ASAP7_75t_R _387_ (.A(_031_),
    .Y(net18));
 INVx1_ASAP7_75t_R _388_ (.A(_072_),
    .Y(net19));
 INVx1_ASAP7_75t_R _389_ (.A(_057_),
    .Y(net20));
 INVx1_ASAP7_75t_R _390_ (.A(_092_),
    .Y(net21));
 INVx1_ASAP7_75t_R _391_ (.A(_003_),
    .Y(\confidence[0] ));
 INVx1_ASAP7_75t_R _392_ (.A(_001_),
    .Y(\confidence[1] ));
 INVx1_ASAP7_75t_R _393_ (.A(_000_),
    .Y(\confidence[2] ));
 INVx1_ASAP7_75t_R _394_ (.A(_094_),
    .Y(_119_));
 INVx1_ASAP7_75t_R _395_ (.A(_020_),
    .Y(_019_));
 OA21x2_ASAP7_75t_R _396_ (.A1(_050_),
    .A2(_019_),
    .B(_049_),
    .Y(_120_));
 OR3x2_ASAP7_75t_R _397_ (.A(_046_),
    .B(_081_),
    .C(_036_),
    .Y(_121_));
 OA21x2_ASAP7_75t_R _398_ (.A1(_046_),
    .A2(_083_),
    .B(_045_),
    .Y(_122_));
 OA21x2_ASAP7_75t_R _399_ (.A1(_036_),
    .A2(_122_),
    .B(_035_),
    .Y(_123_));
 OAI21x1_ASAP7_75t_R _400_ (.A1(_120_),
    .A2(_121_),
    .B(_123_),
    .Y(_124_));
 OR3x1_ASAP7_75t_R _402_ (.A(_091_),
    .B(_043_),
    .C(_059_),
    .Y(_126_));
 OR3x1_ASAP7_75t_R _403_ (.A(_033_),
    .B(_071_),
    .C(_126_),
    .Y(_127_));
 INVx1_ASAP7_75t_R _404_ (.A(_127_),
    .Y(_128_));
 OA21x2_ASAP7_75t_R _405_ (.A1(_032_),
    .A2(_071_),
    .B(_073_),
    .Y(_129_));
 OA21x2_ASAP7_75t_R _406_ (.A1(_091_),
    .A2(_058_),
    .B(_093_),
    .Y(_130_));
 OA21x2_ASAP7_75t_R _407_ (.A1(_043_),
    .A2(_130_),
    .B(_042_),
    .Y(_131_));
 OAI21x1_ASAP7_75t_R _408_ (.A1(_126_),
    .A2(_129_),
    .B(_131_),
    .Y(_132_));
 AO21x1_ASAP7_75t_R _409_ (.A1(_124_),
    .A2(_128_),
    .B(_132_),
    .Y(_133_));
 OR4x1_ASAP7_75t_R _411_ (.A(_033_),
    .B(_050_),
    .C(\above[0] ),
    .D(_071_),
    .Y(_135_));
 OR3x4_ASAP7_75t_R _412_ (.A(_126_),
    .B(_121_),
    .C(_135_),
    .Y(_136_));
 AND2x2_ASAP7_75t_R _413_ (.A(_133_),
    .B(_136_),
    .Y(_137_));
 XNOR2x2_ASAP7_75t_R _414_ (.A(_004_),
    .B(_030_),
    .Y(_138_));
 OA21x2_ASAP7_75t_R _415_ (.A1(\below[1] ),
    .A2(\below[0] ),
    .B(_138_),
    .Y(_139_));
 INVx1_ASAP7_75t_R _416_ (.A(_067_),
    .Y(_140_));
 INVx2_ASAP7_75t_R _417_ (.A(_011_),
    .Y(_010_));
 OA211x2_ASAP7_75t_R _418_ (.A1(_010_),
    .A2(_055_),
    .B(_029_),
    .C(_054_),
    .Y(_141_));
 AND2x2_ASAP7_75t_R _419_ (.A(_029_),
    .B(_030_),
    .Y(_142_));
 NOR3x1_ASAP7_75t_R _420_ (.A(_140_),
    .B(_141_),
    .C(_142_),
    .Y(_143_));
 OA21x2_ASAP7_75t_R _421_ (.A1(_141_),
    .A2(_142_),
    .B(_140_),
    .Y(_144_));
 OR2x2_ASAP7_75t_R _422_ (.A(_143_),
    .B(_144_),
    .Y(_145_));
 INVx1_ASAP7_75t_R _423_ (.A(_004_),
    .Y(_146_));
 OA21x2_ASAP7_75t_R _424_ (.A1(_146_),
    .A2(_030_),
    .B(_029_),
    .Y(_147_));
 OA21x2_ASAP7_75t_R _425_ (.A1(_067_),
    .A2(_147_),
    .B(_066_),
    .Y(_148_));
 XOR2x2_ASAP7_75t_R _426_ (.A(_070_),
    .B(_148_),
    .Y(_149_));
 OR3x1_ASAP7_75t_R _428_ (.A(_053_),
    .B(_070_),
    .C(_067_),
    .Y(_151_));
 OR2x2_ASAP7_75t_R _429_ (.A(_023_),
    .B(_151_),
    .Y(_152_));
 OR3x1_ASAP7_75t_R _430_ (.A(_053_),
    .B(_070_),
    .C(_066_),
    .Y(_153_));
 OA21x2_ASAP7_75t_R _431_ (.A1(_053_),
    .A2(_069_),
    .B(_052_),
    .Y(_154_));
 AO21x1_ASAP7_75t_R _432_ (.A1(_153_),
    .A2(_154_),
    .B(_023_),
    .Y(_155_));
 OA31x2_ASAP7_75t_R _433_ (.A1(_141_),
    .A2(_142_),
    .A3(_152_),
    .B1(_155_),
    .Y(_156_));
 NAND2x1_ASAP7_75t_R _434_ (.A(_022_),
    .B(_156_),
    .Y(_157_));
 AND2x2_ASAP7_75t_R _435_ (.A(_153_),
    .B(_154_),
    .Y(_158_));
 OA21x2_ASAP7_75t_R _436_ (.A1(_151_),
    .A2(_147_),
    .B(_158_),
    .Y(_159_));
 OR3x1_ASAP7_75t_R _437_ (.A(_023_),
    .B(_062_),
    .C(_076_),
    .Y(_160_));
 OR2x2_ASAP7_75t_R _438_ (.A(_022_),
    .B(_062_),
    .Y(_161_));
 AO21x1_ASAP7_75t_R _439_ (.A1(_061_),
    .A2(_161_),
    .B(_076_),
    .Y(_162_));
 AND2x2_ASAP7_75t_R _440_ (.A(_087_),
    .B(_075_),
    .Y(_163_));
 OA211x2_ASAP7_75t_R _441_ (.A1(_159_),
    .A2(_160_),
    .B(_162_),
    .C(_163_),
    .Y(_164_));
 INVx1_ASAP7_75t_R _442_ (.A(_062_),
    .Y(_165_));
 AO32x1_ASAP7_75t_R _443_ (.A1(_022_),
    .A2(_165_),
    .A3(_156_),
    .B1(_088_),
    .B2(_087_),
    .Y(_166_));
 AOI211x1_ASAP7_75t_R _444_ (.A1(_062_),
    .A2(_157_),
    .B(_164_),
    .C(_166_),
    .Y(_167_));
 INVx1_ASAP7_75t_R _445_ (.A(_167_),
    .Y(_168_));
 OR5x1_ASAP7_75t_R _446_ (.A(_137_),
    .B(_139_),
    .C(_145_),
    .D(_149_),
    .E(_168_),
    .Y(_169_));
 OR2x2_ASAP7_75t_R _447_ (.A(\above[0] ),
    .B(\above[1] ),
    .Y(_170_));
 XNOR2x2_ASAP7_75t_R _448_ (.A(_005_),
    .B(_081_),
    .Y(_171_));
 NAND2x1_ASAP7_75t_R _449_ (.A(_170_),
    .B(_171_),
    .Y(_172_));
 INVx1_ASAP7_75t_R _450_ (.A(_046_),
    .Y(_173_));
 OAI21x1_ASAP7_75t_R _451_ (.A1(_081_),
    .A2(_120_),
    .B(_083_),
    .Y(_174_));
 XNOR2x2_ASAP7_75t_R _452_ (.A(_173_),
    .B(_174_),
    .Y(_175_));
 INVx1_ASAP7_75t_R _453_ (.A(_005_),
    .Y(_176_));
 OA21x2_ASAP7_75t_R _454_ (.A1(_176_),
    .A2(_081_),
    .B(_083_),
    .Y(_177_));
 OA21x2_ASAP7_75t_R _455_ (.A1(_046_),
    .A2(_177_),
    .B(_045_),
    .Y(_178_));
 XNOR2x2_ASAP7_75t_R _456_ (.A(_036_),
    .B(_178_),
    .Y(_179_));
 OA211x2_ASAP7_75t_R _457_ (.A1(_176_),
    .A2(_081_),
    .B(_045_),
    .C(_083_),
    .Y(_180_));
 AO21x1_ASAP7_75t_R _458_ (.A1(_046_),
    .A2(_045_),
    .B(_036_),
    .Y(_181_));
 OA21x2_ASAP7_75t_R _459_ (.A1(_180_),
    .A2(_181_),
    .B(_035_),
    .Y(_182_));
 OA21x2_ASAP7_75t_R _460_ (.A1(_033_),
    .A2(_182_),
    .B(_032_),
    .Y(_183_));
 XNOR2x2_ASAP7_75t_R _461_ (.A(_071_),
    .B(_183_),
    .Y(_184_));
 AND5x1_ASAP7_75t_R _462_ (.A(_137_),
    .B(_172_),
    .C(_175_),
    .D(_179_),
    .E(_184_),
    .Y(_185_));
 INVx1_ASAP7_75t_R _463_ (.A(_185_),
    .Y(_186_));
 XNOR2x2_ASAP7_75t_R _464_ (.A(_059_),
    .B(_129_),
    .Y(_187_));
 OA211x2_ASAP7_75t_R _465_ (.A1(_120_),
    .A2(_121_),
    .B(_123_),
    .C(_187_),
    .Y(_188_));
 INVx1_ASAP7_75t_R _466_ (.A(_059_),
    .Y(_189_));
 AND2x2_ASAP7_75t_R _467_ (.A(_071_),
    .B(_073_),
    .Y(_190_));
 XNOR2x2_ASAP7_75t_R _468_ (.A(_189_),
    .B(_190_),
    .Y(_191_));
 NOR2x1_ASAP7_75t_R _469_ (.A(_033_),
    .B(_191_),
    .Y(_192_));
 AO22x1_ASAP7_75t_R _470_ (.A1(_033_),
    .A2(_188_),
    .B1(_192_),
    .B2(_124_),
    .Y(_193_));
 NAND2x1_ASAP7_75t_R _471_ (.A(_058_),
    .B(_129_),
    .Y(_194_));
 AOI22x1_ASAP7_75t_R _472_ (.A1(_058_),
    .A2(_059_),
    .B1(_194_),
    .B2(_043_),
    .Y(_195_));
 INVx1_ASAP7_75t_R _473_ (.A(_091_),
    .Y(_196_));
 INVx1_ASAP7_75t_R _474_ (.A(_093_),
    .Y(_197_));
 OR3x4_ASAP7_75t_R _475_ (.A(_196_),
    .B(_197_),
    .C(_043_),
    .Y(_198_));
 NAND2x1_ASAP7_75t_R _476_ (.A(_197_),
    .B(_043_),
    .Y(_199_));
 OA211x2_ASAP7_75t_R _477_ (.A1(_091_),
    .A2(_195_),
    .B(_198_),
    .C(_199_),
    .Y(_200_));
 NOR2x1_ASAP7_75t_R _478_ (.A(_033_),
    .B(_071_),
    .Y(_201_));
 OR3x1_ASAP7_75t_R _479_ (.A(_197_),
    .B(_043_),
    .C(_194_),
    .Y(_202_));
 AO21x1_ASAP7_75t_R _480_ (.A1(_124_),
    .A2(_201_),
    .B(_202_),
    .Y(_203_));
 AND4x1_ASAP7_75t_R _481_ (.A(_196_),
    .B(_043_),
    .C(_189_),
    .D(_201_),
    .Y(_204_));
 NAND2x1_ASAP7_75t_R _482_ (.A(_124_),
    .B(_204_),
    .Y(_205_));
 AND4x2_ASAP7_75t_R _483_ (.A(_193_),
    .B(_200_),
    .C(_203_),
    .D(_205_),
    .Y(_206_));
 AND3x1_ASAP7_75t_R _484_ (.A(_032_),
    .B(_035_),
    .C(_073_),
    .Y(_207_));
 OA21x2_ASAP7_75t_R _485_ (.A1(_180_),
    .A2(_181_),
    .B(_207_),
    .Y(_208_));
 AND3x1_ASAP7_75t_R _486_ (.A(_032_),
    .B(_033_),
    .C(_073_),
    .Y(_209_));
 OR2x2_ASAP7_75t_R _487_ (.A(_190_),
    .B(_209_),
    .Y(_210_));
 OA31x2_ASAP7_75t_R _488_ (.A1(_059_),
    .A2(_208_),
    .A3(_210_),
    .B1(_058_),
    .Y(_211_));
 AND2x2_ASAP7_75t_R _489_ (.A(_196_),
    .B(_058_),
    .Y(_212_));
 OAI21x1_ASAP7_75t_R _490_ (.A1(_208_),
    .A2(_210_),
    .B(_212_),
    .Y(_213_));
 OA21x2_ASAP7_75t_R _491_ (.A1(_196_),
    .A2(_211_),
    .B(_213_),
    .Y(_214_));
 AND3x1_ASAP7_75t_R _492_ (.A(_137_),
    .B(_206_),
    .C(_214_),
    .Y(_215_));
 NAND2x1_ASAP7_75t_R _493_ (.A(_133_),
    .B(_136_),
    .Y(_216_));
 INVx1_ASAP7_75t_R _494_ (.A(_076_),
    .Y(_217_));
 AND3x1_ASAP7_75t_R _495_ (.A(_088_),
    .B(_165_),
    .C(_217_),
    .Y(_218_));
 INVx1_ASAP7_75t_R _496_ (.A(_088_),
    .Y(_219_));
 AND5x1_ASAP7_75t_R _497_ (.A(_022_),
    .B(_219_),
    .C(_061_),
    .D(_075_),
    .E(_156_),
    .Y(_220_));
 AOI21x1_ASAP7_75t_R _498_ (.A1(_157_),
    .A2(_218_),
    .B(_220_),
    .Y(_221_));
 OAI21x1_ASAP7_75t_R _499_ (.A1(_151_),
    .A2(_147_),
    .B(_158_),
    .Y(_222_));
 NAND2x1_ASAP7_75t_R _500_ (.A(_023_),
    .B(_222_),
    .Y(_223_));
 OR4x1_ASAP7_75t_R _501_ (.A(_023_),
    .B(_062_),
    .C(_217_),
    .D(_159_),
    .Y(_224_));
 AO21x1_ASAP7_75t_R _502_ (.A1(_061_),
    .A2(_062_),
    .B(_076_),
    .Y(_225_));
 OAI21x1_ASAP7_75t_R _503_ (.A1(_022_),
    .A2(_062_),
    .B(_061_),
    .Y(_226_));
 AO32x1_ASAP7_75t_R _504_ (.A1(_219_),
    .A2(_075_),
    .A3(_225_),
    .B1(_226_),
    .B2(_076_),
    .Y(_227_));
 INVx1_ASAP7_75t_R _505_ (.A(_227_),
    .Y(_228_));
 AO21x1_ASAP7_75t_R _506_ (.A1(_061_),
    .A2(_075_),
    .B(_219_),
    .Y(_229_));
 OA211x2_ASAP7_75t_R _507_ (.A1(_023_),
    .A2(_222_),
    .B(_228_),
    .C(_229_),
    .Y(_230_));
 NOR2x1_ASAP7_75t_R _508_ (.A(_023_),
    .B(_062_),
    .Y(_231_));
 AO211x2_ASAP7_75t_R _509_ (.A1(_222_),
    .A2(_231_),
    .B(_076_),
    .C(_226_),
    .Y(_232_));
 OR3x1_ASAP7_75t_R _510_ (.A(_070_),
    .B(_067_),
    .C(_142_),
    .Y(_233_));
 OA21x2_ASAP7_75t_R _511_ (.A1(_070_),
    .A2(_066_),
    .B(_069_),
    .Y(_234_));
 OA21x2_ASAP7_75t_R _512_ (.A1(_141_),
    .A2(_233_),
    .B(_234_),
    .Y(_235_));
 XNOR2x2_ASAP7_75t_R _513_ (.A(_053_),
    .B(_235_),
    .Y(_236_));
 AND5x1_ASAP7_75t_R _514_ (.A(_223_),
    .B(_224_),
    .C(_230_),
    .D(_232_),
    .E(_236_),
    .Y(_237_));
 AND3x1_ASAP7_75t_R _515_ (.A(_216_),
    .B(_221_),
    .C(_237_),
    .Y(_238_));
 NOR2x1_ASAP7_75t_R _516_ (.A(_215_),
    .B(_238_),
    .Y(_239_));
 AO21x1_ASAP7_75t_R _517_ (.A1(_169_),
    .A2(_186_),
    .B(_239_),
    .Y(_240_));
 NOR2x1_ASAP7_75t_R _518_ (.A(_119_),
    .B(_240_),
    .Y(_097_));
 INVx1_ASAP7_75t_R _519_ (.A(net3),
    .Y(_028_));
 INVx1_ASAP7_75t_R _520_ (.A(net2),
    .Y(_012_));
 INVx1_ASAP7_75t_R _521_ (.A(net8),
    .Y(_060_));
 AND3x1_ASAP7_75t_R _522_ (.A(_002_),
    .B(_001_),
    .C(_000_),
    .Y(_241_));
 NOR2x1_ASAP7_75t_R _524_ (.A(_007_),
    .B(_241_),
    .Y(_100_));
 INVx1_ASAP7_75t_R _525_ (.A(net4),
    .Y(_065_));
 INVx1_ASAP7_75t_R _526_ (.A(net9),
    .Y(_074_));
 INVx1_ASAP7_75t_R _527_ (.A(net10),
    .Y(_086_));
 INVx1_ASAP7_75t_R _528_ (.A(net6),
    .Y(_051_));
 OR5x1_ASAP7_75t_R _529_ (.A(\below[1] ),
    .B(\below[0] ),
    .C(_138_),
    .D(_143_),
    .E(_144_),
    .Y(_243_));
 AOI22x1_ASAP7_75t_R _530_ (.A1(_133_),
    .A2(_136_),
    .B1(_149_),
    .B2(_243_),
    .Y(_244_));
 OR3x1_ASAP7_75t_R _531_ (.A(_046_),
    .B(_170_),
    .C(_171_),
    .Y(_245_));
 INVx1_ASAP7_75t_R _532_ (.A(_245_),
    .Y(_246_));
 NOR3x1_ASAP7_75t_R _533_ (.A(_173_),
    .B(_170_),
    .C(_171_),
    .Y(_247_));
 OA211x2_ASAP7_75t_R _534_ (.A1(_081_),
    .A2(_120_),
    .B(_247_),
    .C(_083_),
    .Y(_248_));
 AO21x1_ASAP7_75t_R _535_ (.A1(_174_),
    .A2(_246_),
    .B(_248_),
    .Y(_249_));
 OA211x2_ASAP7_75t_R _536_ (.A1(_179_),
    .A2(_249_),
    .B(_133_),
    .C(_136_),
    .Y(_250_));
 AO22x1_ASAP7_75t_R _537_ (.A1(_167_),
    .A2(_244_),
    .B1(_250_),
    .B2(_184_),
    .Y(_251_));
 OA21x2_ASAP7_75t_R _538_ (.A1(_215_),
    .A2(_238_),
    .B(_251_),
    .Y(near16));
 INVx1_ASAP7_75t_R _539_ (.A(near16),
    .Y(_098_));
 INVx1_ASAP7_75t_R _541_ (.A(net12),
    .Y(_253_));
 INVx1_ASAP7_75t_R _543_ (.A(_002_),
    .Y(_255_));
 OR3x1_ASAP7_75t_R _544_ (.A(_255_),
    .B(\confidence[1] ),
    .C(\confidence[2] ),
    .Y(_256_));
 OA211x2_ASAP7_75t_R _546_ (.A1(\confidence[0] ),
    .A2(_256_),
    .B(near16),
    .C(net12),
    .Y(_258_));
 AOI211x1_ASAP7_75t_R _547_ (.A1(_253_),
    .A2(_008_),
    .B(net11),
    .C(_258_),
    .Y(_101_));
 OR2x2_ASAP7_75t_R _548_ (.A(net12),
    .B(_007_),
    .Y(_259_));
 OR3x1_ASAP7_75t_R _549_ (.A(_253_),
    .B(_008_),
    .C(near16),
    .Y(_260_));
 AOI21x1_ASAP7_75t_R _550_ (.A1(_259_),
    .A2(_260_),
    .B(net11),
    .Y(_102_));
 INVx1_ASAP7_75t_R _551_ (.A(net11),
    .Y(_261_));
 NAND2x1_ASAP7_75t_R _553_ (.A(net12),
    .B(g1_11),
    .Y(_263_));
 AO21x1_ASAP7_75t_R _554_ (.A1(_002_),
    .A2(_000_),
    .B(_263_),
    .Y(_264_));
 OA211x2_ASAP7_75t_R _555_ (.A1(net12),
    .A2(_119_),
    .B(_261_),
    .C(_264_),
    .Y(_103_));
 XNOR2x2_ASAP7_75t_R _556_ (.A(_017_),
    .B(_027_),
    .Y(_265_));
 AOI221x1_ASAP7_75t_R _557_ (.A1(_167_),
    .A2(_244_),
    .B1(_250_),
    .B2(_184_),
    .C(_007_),
    .Y(_266_));
 AOI211x1_ASAP7_75t_R _558_ (.A1(_221_),
    .A2(_237_),
    .B(_007_),
    .C(_137_),
    .Y(_267_));
 AOI211x1_ASAP7_75t_R _559_ (.A1(_206_),
    .A2(_214_),
    .B(_007_),
    .C(_216_),
    .Y(_268_));
 NOR3x1_ASAP7_75t_R _560_ (.A(_266_),
    .B(_267_),
    .C(_268_),
    .Y(_269_));
 AOI21x1_ASAP7_75t_R _561_ (.A1(_003_),
    .A2(_241_),
    .B(do_inc),
    .Y(_270_));
 NAND2x1_ASAP7_75t_R _562_ (.A(net12),
    .B(_270_),
    .Y(_271_));
 AND2x2_ASAP7_75t_R _563_ (.A(net12),
    .B(do_inc),
    .Y(_272_));
 OR4x1_ASAP7_75t_R _564_ (.A(_002_),
    .B(_003_),
    .C(_001_),
    .D(_000_),
    .Y(_273_));
 NAND2x1_ASAP7_75t_R _565_ (.A(_272_),
    .B(_273_),
    .Y(_274_));
 OR4x1_ASAP7_75t_R _566_ (.A(_266_),
    .B(_267_),
    .C(_268_),
    .D(_274_),
    .Y(_275_));
 OAI21x1_ASAP7_75t_R _567_ (.A1(_269_),
    .A2(_271_),
    .B(_275_),
    .Y(_276_));
 OA21x2_ASAP7_75t_R _568_ (.A1(_269_),
    .A2(_271_),
    .B(_000_),
    .Y(_277_));
 AOI221x1_ASAP7_75t_R _569_ (.A1(_265_),
    .A2(_276_),
    .B1(_277_),
    .B2(_275_),
    .C(net11),
    .Y(_104_));
 OA21x2_ASAP7_75t_R _570_ (.A1(_269_),
    .A2(_271_),
    .B(_001_),
    .Y(_278_));
 AOI221x1_ASAP7_75t_R _571_ (.A1(_018_),
    .A2(_276_),
    .B1(_278_),
    .B2(_275_),
    .C(net11),
    .Y(_105_));
 AND3x1_ASAP7_75t_R _572_ (.A(\confidence[0] ),
    .B(_261_),
    .C(_274_),
    .Y(_279_));
 AND3x1_ASAP7_75t_R _573_ (.A(_003_),
    .B(_261_),
    .C(_272_),
    .Y(_280_));
 OA21x2_ASAP7_75t_R _574_ (.A1(_279_),
    .A2(_280_),
    .B(_269_),
    .Y(_281_));
 AND3x1_ASAP7_75t_R _575_ (.A(\confidence[0] ),
    .B(_261_),
    .C(_271_),
    .Y(_282_));
 AND4x1_ASAP7_75t_R _576_ (.A(net12),
    .B(_003_),
    .C(_261_),
    .D(_270_),
    .Y(_283_));
 OR3x1_ASAP7_75t_R _577_ (.A(_266_),
    .B(_267_),
    .C(_268_),
    .Y(_284_));
 OA21x2_ASAP7_75t_R _578_ (.A1(_282_),
    .A2(_283_),
    .B(_284_),
    .Y(_285_));
 OR2x2_ASAP7_75t_R _579_ (.A(_281_),
    .B(_285_),
    .Y(_106_));
 OA21x2_ASAP7_75t_R _580_ (.A1(_014_),
    .A2(_078_),
    .B(_077_),
    .Y(_286_));
 OA21x2_ASAP7_75t_R _581_ (.A1(_040_),
    .A2(_286_),
    .B(_039_),
    .Y(_287_));
 OA21x2_ASAP7_75t_R _582_ (.A1(_064_),
    .A2(_287_),
    .B(_063_),
    .Y(_288_));
 OA21x2_ASAP7_75t_R _583_ (.A1(_085_),
    .A2(_288_),
    .B(_084_),
    .Y(_289_));
 OA21x2_ASAP7_75t_R _584_ (.A1(_080_),
    .A2(_289_),
    .B(_079_),
    .Y(_290_));
 OA21x2_ASAP7_75t_R _585_ (.A1(_048_),
    .A2(_290_),
    .B(_047_),
    .Y(_291_));
 XOR2x2_ASAP7_75t_R _586_ (.A(_038_),
    .B(_291_),
    .Y(_292_));
 AND2x2_ASAP7_75t_R _587_ (.A(net9),
    .B(_241_),
    .Y(_293_));
 AO21x1_ASAP7_75t_R _588_ (.A1(_256_),
    .A2(_292_),
    .B(_293_),
    .Y(_294_));
 INVx1_ASAP7_75t_R _589_ (.A(g1_15),
    .Y(_295_));
 AND4x1_ASAP7_75t_R _590_ (.A(_044_),
    .B(_034_),
    .C(_031_),
    .D(_072_),
    .Y(_296_));
 AND4x1_ASAP7_75t_R _591_ (.A(_041_),
    .B(\stepped[0] ),
    .C(_009_),
    .D(_082_),
    .Y(_297_));
 AND4x1_ASAP7_75t_R _592_ (.A(_057_),
    .B(_092_),
    .C(_296_),
    .D(_297_),
    .Y(_298_));
 INVx1_ASAP7_75t_R _593_ (.A(_298_),
    .Y(_299_));
 AND5x1_ASAP7_75t_R _594_ (.A(_006_),
    .B(_119_),
    .C(_295_),
    .D(do_down),
    .E(_299_),
    .Y(_013_));
 NAND2x1_ASAP7_75t_R _595_ (.A(_006_),
    .B(_119_),
    .Y(_300_));
 OR4x1_ASAP7_75t_R _596_ (.A(_044_),
    .B(_034_),
    .C(_031_),
    .D(_072_),
    .Y(_301_));
 OR4x1_ASAP7_75t_R _597_ (.A(_041_),
    .B(\stepped[0] ),
    .C(_009_),
    .D(_082_),
    .Y(_302_));
 OR4x1_ASAP7_75t_R _598_ (.A(_057_),
    .B(_092_),
    .C(_301_),
    .D(_302_),
    .Y(_303_));
 INVx1_ASAP7_75t_R _599_ (.A(do_down),
    .Y(_304_));
 OA211x2_ASAP7_75t_R _600_ (.A1(g1_15),
    .A2(_300_),
    .B(_303_),
    .C(_304_),
    .Y(_305_));
 OR3x1_ASAP7_75t_R _601_ (.A(_241_),
    .B(_013_),
    .C(_305_),
    .Y(_306_));
 AND3x1_ASAP7_75t_R _602_ (.A(net12),
    .B(_261_),
    .C(_306_),
    .Y(_307_));
 NAND2x1_ASAP7_75t_R _603_ (.A(net12),
    .B(_306_),
    .Y(_308_));
 AND3x1_ASAP7_75t_R _605_ (.A(net21),
    .B(_261_),
    .C(_308_),
    .Y(_310_));
 AO21x1_ASAP7_75t_R _606_ (.A1(_294_),
    .A2(_307_),
    .B(_310_),
    .Y(_107_));
 NAND2x1_ASAP7_75t_R _607_ (.A(_060_),
    .B(_241_),
    .Y(_311_));
 OA21x2_ASAP7_75t_R _608_ (.A1(\stepped[0] ),
    .A2(_090_),
    .B(_089_),
    .Y(_312_));
 OA21x2_ASAP7_75t_R _609_ (.A1(_078_),
    .A2(_312_),
    .B(_077_),
    .Y(_313_));
 OA21x2_ASAP7_75t_R _610_ (.A1(_040_),
    .A2(_313_),
    .B(_039_),
    .Y(_314_));
 AND3x1_ASAP7_75t_R _611_ (.A(_084_),
    .B(_079_),
    .C(_063_),
    .Y(_315_));
 OA21x2_ASAP7_75t_R _612_ (.A1(_064_),
    .A2(_314_),
    .B(_315_),
    .Y(_316_));
 AND3x1_ASAP7_75t_R _613_ (.A(_084_),
    .B(_085_),
    .C(_079_),
    .Y(_317_));
 AO21x1_ASAP7_75t_R _614_ (.A1(_080_),
    .A2(_079_),
    .B(_317_),
    .Y(_318_));
 OAI21x1_ASAP7_75t_R _615_ (.A1(_316_),
    .A2(_318_),
    .B(_048_),
    .Y(_319_));
 OR3x1_ASAP7_75t_R _616_ (.A(_048_),
    .B(_316_),
    .C(_318_),
    .Y(_320_));
 AO21x1_ASAP7_75t_R _617_ (.A1(_319_),
    .A2(_320_),
    .B(_241_),
    .Y(_321_));
 NOR2x1_ASAP7_75t_R _618_ (.A(_057_),
    .B(net11),
    .Y(_322_));
 AO32x1_ASAP7_75t_R _619_ (.A1(_307_),
    .A2(_311_),
    .A3(_321_),
    .B1(_322_),
    .B2(_308_),
    .Y(_108_));
 INVx1_ASAP7_75t_R _620_ (.A(_308_),
    .Y(_323_));
 INVx1_ASAP7_75t_R _621_ (.A(net7),
    .Y(_021_));
 NAND2x1_ASAP7_75t_R _622_ (.A(_021_),
    .B(_241_),
    .Y(_324_));
 XNOR2x2_ASAP7_75t_R _623_ (.A(_080_),
    .B(_289_),
    .Y(_325_));
 NAND2x1_ASAP7_75t_R _624_ (.A(_256_),
    .B(_325_),
    .Y(_326_));
 AO21x1_ASAP7_75t_R _625_ (.A1(_324_),
    .A2(_326_),
    .B(_308_),
    .Y(_327_));
 OA211x2_ASAP7_75t_R _626_ (.A1(net19),
    .A2(_323_),
    .B(_327_),
    .C(_261_),
    .Y(_109_));
 NAND2x1_ASAP7_75t_R _627_ (.A(_051_),
    .B(_241_),
    .Y(_328_));
 OA21x2_ASAP7_75t_R _628_ (.A1(_064_),
    .A2(_314_),
    .B(_063_),
    .Y(_329_));
 XNOR2x2_ASAP7_75t_R _629_ (.A(_085_),
    .B(_329_),
    .Y(_330_));
 NAND2x1_ASAP7_75t_R _630_ (.A(_256_),
    .B(_330_),
    .Y(_331_));
 AO21x1_ASAP7_75t_R _631_ (.A1(_328_),
    .A2(_331_),
    .B(_308_),
    .Y(_332_));
 OA211x2_ASAP7_75t_R _632_ (.A1(net18),
    .A2(_323_),
    .B(_332_),
    .C(_261_),
    .Y(_110_));
 INVx1_ASAP7_75t_R _633_ (.A(net5),
    .Y(_068_));
 NAND2x1_ASAP7_75t_R _634_ (.A(_068_),
    .B(_241_),
    .Y(_333_));
 XNOR2x2_ASAP7_75t_R _635_ (.A(_064_),
    .B(_287_),
    .Y(_334_));
 NAND2x1_ASAP7_75t_R _636_ (.A(_256_),
    .B(_334_),
    .Y(_335_));
 AO21x1_ASAP7_75t_R _637_ (.A1(_333_),
    .A2(_335_),
    .B(_308_),
    .Y(_336_));
 OA211x2_ASAP7_75t_R _638_ (.A1(net17),
    .A2(_323_),
    .B(_336_),
    .C(_261_),
    .Y(_111_));
 NAND2x1_ASAP7_75t_R _639_ (.A(_065_),
    .B(_241_),
    .Y(_337_));
 XNOR2x2_ASAP7_75t_R _640_ (.A(_040_),
    .B(_313_),
    .Y(_338_));
 NAND2x1_ASAP7_75t_R _641_ (.A(_256_),
    .B(_338_),
    .Y(_339_));
 AO21x1_ASAP7_75t_R _642_ (.A1(_337_),
    .A2(_339_),
    .B(_308_),
    .Y(_340_));
 OA211x2_ASAP7_75t_R _643_ (.A1(net16),
    .A2(_323_),
    .B(_340_),
    .C(_261_),
    .Y(_112_));
 NAND2x1_ASAP7_75t_R _644_ (.A(_028_),
    .B(_241_),
    .Y(_341_));
 XOR2x2_ASAP7_75t_R _645_ (.A(_014_),
    .B(_078_),
    .Y(_342_));
 OR2x2_ASAP7_75t_R _646_ (.A(_241_),
    .B(_342_),
    .Y(_343_));
 AO21x1_ASAP7_75t_R _647_ (.A1(_341_),
    .A2(_343_),
    .B(_308_),
    .Y(_344_));
 OA211x2_ASAP7_75t_R _648_ (.A1(net15),
    .A2(_323_),
    .B(_344_),
    .C(_261_),
    .Y(_113_));
 OR2x2_ASAP7_75t_R _649_ (.A(_015_),
    .B(_241_),
    .Y(_345_));
 OA211x2_ASAP7_75t_R _650_ (.A1(_012_),
    .A2(_256_),
    .B(_323_),
    .C(_345_),
    .Y(_346_));
 AOI211x1_ASAP7_75t_R _651_ (.A1(_009_),
    .A2(_308_),
    .B(_346_),
    .C(net11),
    .Y(_114_));
 OA21x2_ASAP7_75t_R _652_ (.A1(net1),
    .A2(_256_),
    .B(_323_),
    .Y(_347_));
 AO21x1_ASAP7_75t_R _653_ (.A1(net1),
    .A2(_241_),
    .B(\stepped[0] ),
    .Y(_348_));
 OA21x2_ASAP7_75t_R _654_ (.A1(_308_),
    .A2(_348_),
    .B(_261_),
    .Y(_349_));
 OA21x2_ASAP7_75t_R _655_ (.A1(net13),
    .A2(_347_),
    .B(_349_),
    .Y(_115_));
 INVx1_ASAP7_75t_R _656_ (.A(g1_3),
    .Y(_096_));
 AND2x2_ASAP7_75t_R _657_ (.A(_255_),
    .B(_133_),
    .Y(_095_));
 INVx1_ASAP7_75t_R _658_ (.A(net1),
    .Y(_056_));
 AO21x1_ASAP7_75t_R _659_ (.A1(_133_),
    .A2(_136_),
    .B(_094_),
    .Y(g0_15));
 AND2x2_ASAP7_75t_R _660_ (.A(_133_),
    .B(_240_),
    .Y(g0_8));
 NAND2x1_ASAP7_75t_R _661_ (.A(_133_),
    .B(_240_),
    .Y(_099_));
 AND2x2_ASAP7_75t_R _662_ (.A(_284_),
    .B(_270_),
    .Y(_016_));
 NAND2x1_ASAP7_75t_R _663_ (.A(_253_),
    .B(_006_),
    .Y(_350_));
 OA211x2_ASAP7_75t_R _664_ (.A1(_253_),
    .A2(_133_),
    .B(_350_),
    .C(_261_),
    .Y(_116_));
 OA21x2_ASAP7_75t_R _665_ (.A1(_003_),
    .A2(_025_),
    .B(_024_),
    .Y(_351_));
 OA21x2_ASAP7_75t_R _666_ (.A1(_027_),
    .A2(_351_),
    .B(_026_),
    .Y(_352_));
 AND3x1_ASAP7_75t_R _667_ (.A(net12),
    .B(_270_),
    .C(_352_),
    .Y(_353_));
 OR3x1_ASAP7_75t_R _668_ (.A(_002_),
    .B(net11),
    .C(_353_),
    .Y(_354_));
 INVx1_ASAP7_75t_R _669_ (.A(_352_),
    .Y(_355_));
 OR4x1_ASAP7_75t_R _670_ (.A(_255_),
    .B(net11),
    .C(_271_),
    .D(_355_),
    .Y(_356_));
 AOI21x1_ASAP7_75t_R _671_ (.A1(_354_),
    .A2(_356_),
    .B(_269_),
    .Y(_357_));
 OR2x2_ASAP7_75t_R _672_ (.A(_274_),
    .B(_352_),
    .Y(_358_));
 AND4x2_ASAP7_75t_R _673_ (.A(_255_),
    .B(_261_),
    .C(_269_),
    .D(_358_),
    .Y(_359_));
 AND5x1_ASAP7_75t_R _674_ (.A(_002_),
    .B(_261_),
    .C(_269_),
    .D(_272_),
    .E(_355_),
    .Y(_360_));
 OR3x2_ASAP7_75t_R _675_ (.A(_357_),
    .B(_359_),
    .C(_360_),
    .Y(_117_));
 OA31x2_ASAP7_75t_R _676_ (.A1(_048_),
    .A2(_316_),
    .A3(_318_),
    .B1(_047_),
    .Y(_361_));
 OA21x2_ASAP7_75t_R _677_ (.A1(_038_),
    .A2(_361_),
    .B(_037_),
    .Y(_362_));
 XOR2x2_ASAP7_75t_R _678_ (.A(_013_),
    .B(_362_),
    .Y(_363_));
 NOR2x1_ASAP7_75t_R _679_ (.A(_041_),
    .B(net11),
    .Y(_364_));
 AND3x1_ASAP7_75t_R _680_ (.A(_256_),
    .B(_363_),
    .C(_364_),
    .Y(_365_));
 OR4x1_ASAP7_75t_R _681_ (.A(net22),
    .B(net11),
    .C(_241_),
    .D(_308_),
    .Y(_366_));
 NOR2x1_ASAP7_75t_R _682_ (.A(_363_),
    .B(_366_),
    .Y(_367_));
 AND4x1_ASAP7_75t_R _683_ (.A(net12),
    .B(net10),
    .C(_261_),
    .D(_241_),
    .Y(_368_));
 AO21x1_ASAP7_75t_R _684_ (.A1(_308_),
    .A2(_364_),
    .B(_368_),
    .Y(_369_));
 OR3x1_ASAP7_75t_R _685_ (.A(_365_),
    .B(_367_),
    .C(_369_),
    .Y(_118_));
 FAx1_ASAP7_75t_R _686_ (.SN(\below[1] ),
    .A(net2),
    .B(_009_),
    .CI(_010_),
    .CON(_004_));
 FAx1_ASAP7_75t_R _687_ (.SN(_015_),
    .A(net13),
    .B(net14),
    .CI(_013_),
    .CON(_014_));
 FAx1_ASAP7_75t_R _688_ (.SN(_018_),
    .A(\confidence[0] ),
    .B(\confidence[1] ),
    .CI(_016_),
    .CON(_017_));
 FAx1_ASAP7_75t_R _689_ (.SN(\above[1] ),
    .A(_012_),
    .B(net14),
    .CI(_019_),
    .CON(_005_));
 HAxp5_ASAP7_75t_R _690_ (.A(net19),
    .B(_021_),
    .CON(_022_),
    .SN(_023_));
 HAxp5_ASAP7_75t_R _691_ (.A(\confidence[1] ),
    .B(_016_),
    .CON(_024_),
    .SN(_025_));
 HAxp5_ASAP7_75t_R _692_ (.A(\confidence[2] ),
    .B(_016_),
    .CON(_026_),
    .SN(_027_));
 HAxp5_ASAP7_75t_R _693_ (.A(net15),
    .B(_028_),
    .CON(_029_),
    .SN(_030_));
 HAxp5_ASAP7_75t_R _694_ (.A(net6),
    .B(_031_),
    .CON(_032_),
    .SN(_033_));
 HAxp5_ASAP7_75t_R _695_ (.A(net5),
    .B(_034_),
    .CON(_035_),
    .SN(_036_));
 HAxp5_ASAP7_75t_R _696_ (.A(net21),
    .B(_013_),
    .CON(_037_),
    .SN(_038_));
 HAxp5_ASAP7_75t_R _697_ (.A(net16),
    .B(_013_),
    .CON(_039_),
    .SN(_040_));
 HAxp5_ASAP7_75t_R _698_ (.A(net10),
    .B(_041_),
    .CON(_042_),
    .SN(_043_));
 HAxp5_ASAP7_75t_R _699_ (.A(net4),
    .B(_044_),
    .CON(_045_),
    .SN(_046_));
 HAxp5_ASAP7_75t_R _700_ (.A(net20),
    .B(_013_),
    .CON(_047_),
    .SN(_048_));
 HAxp5_ASAP7_75t_R _701_ (.A(net2),
    .B(_009_),
    .CON(_049_),
    .SN(_050_));
 HAxp5_ASAP7_75t_R _702_ (.A(_051_),
    .B(net18),
    .CON(_052_),
    .SN(_053_));
 HAxp5_ASAP7_75t_R _703_ (.A(_012_),
    .B(net14),
    .CON(_054_),
    .SN(_055_));
 HAxp5_ASAP7_75t_R _704_ (.A(\stepped[0] ),
    .B(net1),
    .CON(_011_),
    .SN(\below[0] ));
 HAxp5_ASAP7_75t_R _705_ (.A(net8),
    .B(_057_),
    .CON(_058_),
    .SN(_059_));
 HAxp5_ASAP7_75t_R _706_ (.A(_060_),
    .B(net20),
    .CON(_061_),
    .SN(_062_));
 HAxp5_ASAP7_75t_R _707_ (.A(net17),
    .B(_013_),
    .CON(_063_),
    .SN(_064_));
 HAxp5_ASAP7_75t_R _708_ (.A(_065_),
    .B(net16),
    .CON(_066_),
    .SN(_067_));
 HAxp5_ASAP7_75t_R _709_ (.A(_068_),
    .B(net17),
    .CON(_069_),
    .SN(_070_));
 HAxp5_ASAP7_75t_R _710_ (.A(_021_),
    .B(net19),
    .CON(_370_),
    .SN(_071_));
 HAxp5_ASAP7_75t_R _711_ (.A(net7),
    .B(_072_),
    .CON(_073_),
    .SN(_371_));
 HAxp5_ASAP7_75t_R _712_ (.A(net21),
    .B(_074_),
    .CON(_075_),
    .SN(_076_));
 HAxp5_ASAP7_75t_R _713_ (.A(net15),
    .B(_013_),
    .CON(_077_),
    .SN(_078_));
 HAxp5_ASAP7_75t_R _714_ (.A(net19),
    .B(_013_),
    .CON(_079_),
    .SN(_080_));
 HAxp5_ASAP7_75t_R _715_ (.A(_028_),
    .B(net15),
    .CON(_372_),
    .SN(_081_));
 HAxp5_ASAP7_75t_R _716_ (.A(net3),
    .B(_082_),
    .CON(_083_),
    .SN(_373_));
 HAxp5_ASAP7_75t_R _717_ (.A(net18),
    .B(_013_),
    .CON(_084_),
    .SN(_085_));
 HAxp5_ASAP7_75t_R _718_ (.A(_056_),
    .B(net13),
    .CON(_020_),
    .SN(\above[0] ));
 HAxp5_ASAP7_75t_R _719_ (.A(_086_),
    .B(net22),
    .CON(_087_),
    .SN(_088_));
 HAxp5_ASAP7_75t_R _720_ (.A(net14),
    .B(_013_),
    .CON(_089_),
    .SN(_090_));
 HAxp5_ASAP7_75t_R _721_ (.A(_074_),
    .B(net21),
    .CON(_374_),
    .SN(_091_));
 HAxp5_ASAP7_75t_R _722_ (.A(net9),
    .B(_092_),
    .CON(_093_),
    .SN(_375_));
 HAxp5_ASAP7_75t_R _723_ (.A(_094_),
    .B(_095_),
    .CON(g1_3),
    .SN(_376_));
 HAxp5_ASAP7_75t_R _724_ (.A(_097_),
    .B(g0_15),
    .CON(_377_),
    .SN(g1_11));
 HAxp5_ASAP7_75t_R _725_ (.A(_098_),
    .B(_099_),
    .CON(_378_),
    .SN(g1_15));
 HAxp5_ASAP7_75t_R _726_ (.A(near16),
    .B(g0_8),
    .CON(do_down),
    .SN(_379_));
 HAxp5_ASAP7_75t_R _727_ (.A(_100_),
    .B(_096_),
    .CON(_380_),
    .SN(do_inc));
 DFFHQNx1_ASAP7_75t_R \candidate[0]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_115_),
    .QN(\stepped[0] ));
 DFFHQNx1_ASAP7_75t_R \candidate[1]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_114_),
    .QN(_009_));
 DFFHQNx1_ASAP7_75t_R \candidate[2]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_113_),
    .QN(_082_));
 DFFHQNx1_ASAP7_75t_R \candidate[3]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_112_),
    .QN(_044_));
 DFFHQNx1_ASAP7_75t_R \candidate[4]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_111_),
    .QN(_034_));
 DFFHQNx1_ASAP7_75t_R \candidate[5]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_110_),
    .QN(_031_));
 DFFHQNx1_ASAP7_75t_R \candidate[6]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_109_),
    .QN(_072_));
 DFFHQNx1_ASAP7_75t_R \candidate[7]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_108_),
    .QN(_057_));
 DFFHQNx1_ASAP7_75t_R \candidate[8]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_107_),
    .QN(_092_));
 DFFHQNx1_ASAP7_75t_R \candidate[9]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_118_),
    .QN(_041_));
 BUFx2_ASAP7_75t_R clkbuf_0_clk (.A(clk),
    .Y(clknet_0_clk));
 BUFx2_ASAP7_75t_R clkbuf_1_0__f_clk (.A(clknet_0_clk),
    .Y(clknet_1_0__leaf_clk));
 BUFx2_ASAP7_75t_R clkbuf_1_1__f_clk (.A(clknet_0_clk),
    .Y(clknet_1_1__leaf_clk));
 DFFHQNx1_ASAP7_75t_R \confidence[0]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_106_),
    .QN(_003_));
 DFFHQNx1_ASAP7_75t_R \confidence[1]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_105_),
    .QN(_001_));
 DFFHQNx1_ASAP7_75t_R \confidence[2]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_104_),
    .QN(_000_));
 DFFHQNx1_ASAP7_75t_R \confidence[3]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_117_),
    .QN(_002_));
 BUFx3_ASAP7_75t_R input1 (.A(arrival[0]),
    .Y(net1));
 BUFx3_ASAP7_75t_R input10 (.A(arrival[9]),
    .Y(net10));
 BUFx3_ASAP7_75t_R input11 (.A(rst),
    .Y(net11));
 BUFx3_ASAP7_75t_R input12 (.A(valid),
    .Y(net12));
 BUFx3_ASAP7_75t_R input2 (.A(arrival[1]),
    .Y(net2));
 BUFx3_ASAP7_75t_R input3 (.A(arrival[2]),
    .Y(net3));
 BUFx3_ASAP7_75t_R input4 (.A(arrival[3]),
    .Y(net4));
 BUFx3_ASAP7_75t_R input5 (.A(arrival[4]),
    .Y(net5));
 BUFx3_ASAP7_75t_R input6 (.A(arrival[5]),
    .Y(net6));
 BUFx3_ASAP7_75t_R input7 (.A(arrival[6]),
    .Y(net7));
 BUFx3_ASAP7_75t_R input8 (.A(arrival[7]),
    .Y(net8));
 BUFx3_ASAP7_75t_R input9 (.A(arrival[8]),
    .Y(net9));
 BUFx3_ASAP7_75t_R output13 (.A(net13),
    .Y(candidate[0]));
 BUFx3_ASAP7_75t_R output14 (.A(net14),
    .Y(candidate[1]));
 BUFx3_ASAP7_75t_R output15 (.A(net15),
    .Y(candidate[2]));
 BUFx3_ASAP7_75t_R output16 (.A(net16),
    .Y(candidate[3]));
 BUFx3_ASAP7_75t_R output17 (.A(net17),
    .Y(candidate[4]));
 BUFx3_ASAP7_75t_R output18 (.A(net18),
    .Y(candidate[5]));
 BUFx3_ASAP7_75t_R output19 (.A(net19),
    .Y(candidate[6]));
 BUFx3_ASAP7_75t_R output20 (.A(net20),
    .Y(candidate[7]));
 BUFx3_ASAP7_75t_R output21 (.A(net21),
    .Y(candidate[8]));
 BUFx3_ASAP7_75t_R output22 (.A(net22),
    .Y(candidate[9]));
 DFFHQNx1_ASAP7_75t_R \state[0]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_103_),
    .QN(_094_));
 DFFHQNx1_ASAP7_75t_R \state[1]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_102_),
    .QN(_007_));
 DFFHQNx1_ASAP7_75t_R \state[2]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_101_),
    .QN(_008_));
 DFFHQNx1_ASAP7_75t_R \state[3]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_116_),
    .QN(_006_));
endmodule
