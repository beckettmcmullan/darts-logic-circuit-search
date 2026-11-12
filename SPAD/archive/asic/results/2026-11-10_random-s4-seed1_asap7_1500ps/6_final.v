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
 wire _125_;
 wire _126_;
 wire _127_;
 wire _128_;
 wire _129_;
 wire _130_;
 wire _131_;
 wire _132_;
 wire _133_;
 wire _134_;
 wire _135_;
 wire _136_;
 wire _137_;
 wire _138_;
 wire _139_;
 wire _141_;
 wire _142_;
 wire _143_;
 wire _145_;
 wire _146_;
 wire _147_;
 wire _148_;
 wire _149_;
 wire _150_;
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
 wire _237_;
 wire _238_;
 wire _239_;
 wire _240_;
 wire _241_;
 wire _242_;
 wire _243_;
 wire _244_;
 wire _246_;
 wire _247_;
 wire _248_;
 wire _250_;
 wire _251_;
 wire _252_;
 wire _253_;
 wire _254_;
 wire _255_;
 wire _256_;
 wire _257_;
 wire _258_;
 wire _259_;
 wire _260_;
 wire _261_;
 wire _262_;
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
 wire _275_;
 wire _276_;
 wire _277_;
 wire _278_;
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
 wire _309_;
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
 wire do_up;
 wire g1_11;
 wire g1_7;
 wire net11;
 wire \stepped[0] ;
 wire net12;
 wire clknet_0_clk;
 wire clknet_1_0__leaf_clk;
 wire clknet_1_1__leaf_clk;

 INVx1_ASAP7_75t_R _363_ (.A(_046_),
    .Y(net22));
 INVx1_ASAP7_75t_R _364_ (.A(_002_),
    .Y(_111_));
 OA21x2_ASAP7_75t_R _365_ (.A1(_111_),
    .A2(_077_),
    .B(_076_),
    .Y(_112_));
 OR3x1_ASAP7_75t_R _366_ (.A(_080_),
    .B(_020_),
    .C(_074_),
    .Y(_113_));
 OR2x2_ASAP7_75t_R _367_ (.A(_080_),
    .B(_019_),
    .Y(_114_));
 AO21x1_ASAP7_75t_R _368_ (.A1(_079_),
    .A2(_114_),
    .B(_074_),
    .Y(_115_));
 OA21x2_ASAP7_75t_R _369_ (.A1(_112_),
    .A2(_113_),
    .B(_115_),
    .Y(_116_));
 AND3x1_ASAP7_75t_R _370_ (.A(_025_),
    .B(_073_),
    .C(_070_),
    .Y(_117_));
 AND3x1_ASAP7_75t_R _371_ (.A(_025_),
    .B(_071_),
    .C(_070_),
    .Y(_118_));
 AO221x1_ASAP7_75t_R _372_ (.A1(_025_),
    .A2(_026_),
    .B1(_116_),
    .B2(_117_),
    .C(_118_),
    .Y(_119_));
 XNOR2x2_ASAP7_75t_R _373_ (.A(_058_),
    .B(_119_),
    .Y(_120_));
 INVx1_ASAP7_75t_R _374_ (.A(_011_),
    .Y(_010_));
 OA21x2_ASAP7_75t_R _375_ (.A1(_010_),
    .A2(_031_),
    .B(_030_),
    .Y(_121_));
 OA21x2_ASAP7_75t_R _376_ (.A1(_077_),
    .A2(_121_),
    .B(_076_),
    .Y(_122_));
 OA21x2_ASAP7_75t_R _377_ (.A1(_071_),
    .A2(_073_),
    .B(_070_),
    .Y(_123_));
 AND3x1_ASAP7_75t_R _378_ (.A(_079_),
    .B(_019_),
    .C(_123_),
    .Y(_124_));
 AO21x1_ASAP7_75t_R _379_ (.A1(_080_),
    .A2(_079_),
    .B(_074_),
    .Y(_125_));
 AO21x1_ASAP7_75t_R _380_ (.A1(_073_),
    .A2(_125_),
    .B(_071_),
    .Y(_126_));
 AND4x1_ASAP7_75t_R _381_ (.A(_079_),
    .B(_019_),
    .C(_020_),
    .D(_123_),
    .Y(_127_));
 AO21x1_ASAP7_75t_R _382_ (.A1(_070_),
    .A2(_126_),
    .B(_127_),
    .Y(_128_));
 AO21x1_ASAP7_75t_R _383_ (.A1(_122_),
    .A2(_124_),
    .B(_128_),
    .Y(_129_));
 INVx1_ASAP7_75t_R _384_ (.A(_063_),
    .Y(_130_));
 AND3x1_ASAP7_75t_R _385_ (.A(_025_),
    .B(_130_),
    .C(_057_),
    .Y(_131_));
 OR3x1_ASAP7_75t_R _386_ (.A(_130_),
    .B(_026_),
    .C(_058_),
    .Y(_132_));
 AOI211x1_ASAP7_75t_R _387_ (.A1(_122_),
    .A2(_124_),
    .B(_128_),
    .C(_132_),
    .Y(_133_));
 AOI21x1_ASAP7_75t_R _388_ (.A1(_129_),
    .A2(_131_),
    .B(_133_),
    .Y(_134_));
 INVx1_ASAP7_75t_R _389_ (.A(_014_),
    .Y(_013_));
 OA21x2_ASAP7_75t_R _390_ (.A1(_042_),
    .A2(_013_),
    .B(_043_),
    .Y(_135_));
 OR3x1_ASAP7_75t_R _391_ (.A(_017_),
    .B(_066_),
    .C(_052_),
    .Y(_136_));
 OA21x2_ASAP7_75t_R _392_ (.A1(_016_),
    .A2(_052_),
    .B(_054_),
    .Y(_137_));
 OA21x2_ASAP7_75t_R _393_ (.A1(_066_),
    .A2(_137_),
    .B(_065_),
    .Y(_138_));
 OA21x2_ASAP7_75t_R _394_ (.A1(_135_),
    .A2(_136_),
    .B(_138_),
    .Y(_139_));
 OR4x1_ASAP7_75t_R _396_ (.A(_083_),
    .B(_027_),
    .C(_051_),
    .D(_023_),
    .Y(_141_));
 OR2x6_ASAP7_75t_R _397_ (.A(_048_),
    .B(_141_),
    .Y(_142_));
 NOR2x1_ASAP7_75t_R _398_ (.A(_027_),
    .B(_051_),
    .Y(_143_));
 OAI21x1_ASAP7_75t_R _400_ (.A1(_085_),
    .A2(_023_),
    .B(_022_),
    .Y(_145_));
 OAI21x1_ASAP7_75t_R _401_ (.A1(_029_),
    .A2(_051_),
    .B(_050_),
    .Y(_146_));
 AOI21x1_ASAP7_75t_R _402_ (.A1(_143_),
    .A2(_145_),
    .B(_146_),
    .Y(_147_));
 OA21x2_ASAP7_75t_R _403_ (.A1(_048_),
    .A2(_147_),
    .B(_047_),
    .Y(_148_));
 OA21x2_ASAP7_75t_R _404_ (.A1(_139_),
    .A2(_142_),
    .B(_148_),
    .Y(_149_));
 INVx8_ASAP7_75t_R _406_ (.A(_149_),
    .Y(_089_));
 OR4x1_ASAP7_75t_R _407_ (.A(_042_),
    .B(_017_),
    .C(_066_),
    .D(_052_),
    .Y(_150_));
 OR3x4_ASAP7_75t_R _408_ (.A(\above[0] ),
    .B(_142_),
    .C(_150_),
    .Y(_151_));
 AO21x1_ASAP7_75t_R _409_ (.A1(_025_),
    .A2(_026_),
    .B(_058_),
    .Y(_152_));
 AO21x1_ASAP7_75t_R _410_ (.A1(_057_),
    .A2(_152_),
    .B(_063_),
    .Y(_153_));
 INVx1_ASAP7_75t_R _411_ (.A(_057_),
    .Y(_154_));
 NOR2x1_ASAP7_75t_R _412_ (.A(_025_),
    .B(_058_),
    .Y(_155_));
 OR4x1_ASAP7_75t_R _413_ (.A(_130_),
    .B(_062_),
    .C(_154_),
    .D(_155_),
    .Y(_156_));
 AO21x1_ASAP7_75t_R _414_ (.A1(_073_),
    .A2(_074_),
    .B(_071_),
    .Y(_157_));
 NAND2x1_ASAP7_75t_R _415_ (.A(_070_),
    .B(_157_),
    .Y(_158_));
 XNOR2x2_ASAP7_75t_R _416_ (.A(_026_),
    .B(_158_),
    .Y(_159_));
 AOI221x1_ASAP7_75t_R _417_ (.A1(_089_),
    .A2(_151_),
    .B1(_153_),
    .B2(_156_),
    .C(_159_),
    .Y(_160_));
 AND2x2_ASAP7_75t_R _418_ (.A(_073_),
    .B(_116_),
    .Y(_161_));
 XNOR2x2_ASAP7_75t_R _419_ (.A(_071_),
    .B(_161_),
    .Y(_162_));
 AND2x2_ASAP7_75t_R _420_ (.A(_080_),
    .B(_079_),
    .Y(_163_));
 OR4x1_ASAP7_75t_R _421_ (.A(_077_),
    .B(_020_),
    .C(_163_),
    .D(_121_),
    .Y(_164_));
 OR3x1_ASAP7_75t_R _422_ (.A(_076_),
    .B(_020_),
    .C(_163_),
    .Y(_165_));
 OA211x2_ASAP7_75t_R _423_ (.A1(_080_),
    .A2(_019_),
    .B(_165_),
    .C(_079_),
    .Y(_166_));
 NAND2x1_ASAP7_75t_R _424_ (.A(_164_),
    .B(_166_),
    .Y(_167_));
 XOR2x1_ASAP7_75t_R _425_ (.A(_074_),
    .Y(_168_),
    .B(_167_));
 AND5x1_ASAP7_75t_R _426_ (.A(_120_),
    .B(_134_),
    .C(_160_),
    .D(_162_),
    .E(_168_),
    .Y(_169_));
 AND2x2_ASAP7_75t_R _427_ (.A(_089_),
    .B(_151_),
    .Y(_170_));
 INVx1_ASAP7_75t_R _428_ (.A(_051_),
    .Y(_171_));
 INVx1_ASAP7_75t_R _429_ (.A(_003_),
    .Y(_172_));
 AND2x2_ASAP7_75t_R _430_ (.A(_016_),
    .B(_054_),
    .Y(_173_));
 OAI21x1_ASAP7_75t_R _431_ (.A1(_017_),
    .A2(_172_),
    .B(_173_),
    .Y(_174_));
 AOI21x1_ASAP7_75t_R _432_ (.A1(_052_),
    .A2(_054_),
    .B(_066_),
    .Y(_175_));
 NAND2x1_ASAP7_75t_R _433_ (.A(_174_),
    .B(_175_),
    .Y(_176_));
 AND4x1_ASAP7_75t_R _434_ (.A(_085_),
    .B(_065_),
    .C(_022_),
    .D(_176_),
    .Y(_177_));
 AND3x1_ASAP7_75t_R _435_ (.A(_083_),
    .B(_085_),
    .C(_022_),
    .Y(_178_));
 AO21x1_ASAP7_75t_R _436_ (.A1(_023_),
    .A2(_022_),
    .B(_178_),
    .Y(_179_));
 OR4x1_ASAP7_75t_R _437_ (.A(_027_),
    .B(_171_),
    .C(_177_),
    .D(_179_),
    .Y(_180_));
 INVx1_ASAP7_75t_R _438_ (.A(_047_),
    .Y(_181_));
 AND3x1_ASAP7_75t_R _439_ (.A(_181_),
    .B(_048_),
    .C(_147_),
    .Y(_182_));
 OAI21x1_ASAP7_75t_R _440_ (.A1(_139_),
    .A2(_141_),
    .B(_182_),
    .Y(_183_));
 OA22x2_ASAP7_75t_R _441_ (.A1(_139_),
    .A2(_142_),
    .B1(_147_),
    .B2(_048_),
    .Y(_184_));
 NAND2x1_ASAP7_75t_R _442_ (.A(_183_),
    .B(_184_),
    .Y(_185_));
 INVx1_ASAP7_75t_R _443_ (.A(_023_),
    .Y(_186_));
 AND3x1_ASAP7_75t_R _444_ (.A(_085_),
    .B(_065_),
    .C(_186_),
    .Y(_187_));
 NAND2x1_ASAP7_75t_R _445_ (.A(_176_),
    .B(_187_),
    .Y(_188_));
 OAI21x1_ASAP7_75t_R _446_ (.A1(_135_),
    .A2(_136_),
    .B(_138_),
    .Y(_189_));
 NAND2x1_ASAP7_75t_R _447_ (.A(_027_),
    .B(_186_),
    .Y(_190_));
 AO21x1_ASAP7_75t_R _448_ (.A1(_189_),
    .A2(_190_),
    .B(_083_),
    .Y(_191_));
 INVx1_ASAP7_75t_R _449_ (.A(_027_),
    .Y(_192_));
 AND3x1_ASAP7_75t_R _450_ (.A(_192_),
    .B(_085_),
    .C(_022_),
    .Y(_193_));
 OAI21x1_ASAP7_75t_R _451_ (.A1(_189_),
    .A2(_193_),
    .B(_083_),
    .Y(_194_));
 OAI21x1_ASAP7_75t_R _452_ (.A1(_083_),
    .A2(_065_),
    .B(_085_),
    .Y(_195_));
 AO21x1_ASAP7_75t_R _453_ (.A1(_192_),
    .A2(_022_),
    .B(_195_),
    .Y(_196_));
 INVx1_ASAP7_75t_R _454_ (.A(_029_),
    .Y(_197_));
 AND2x2_ASAP7_75t_R _455_ (.A(_047_),
    .B(_050_),
    .Y(_198_));
 OR3x1_ASAP7_75t_R _456_ (.A(_197_),
    .B(_171_),
    .C(_198_),
    .Y(_199_));
 AO21x1_ASAP7_75t_R _457_ (.A1(_029_),
    .A2(_027_),
    .B(_051_),
    .Y(_200_));
 AO32x1_ASAP7_75t_R _458_ (.A1(_083_),
    .A2(_085_),
    .A3(_186_),
    .B1(_145_),
    .B2(_027_),
    .Y(_201_));
 AO221x1_ASAP7_75t_R _459_ (.A1(_023_),
    .A2(_196_),
    .B1(_199_),
    .B2(_200_),
    .C(_201_),
    .Y(_202_));
 INVx1_ASAP7_75t_R _460_ (.A(_083_),
    .Y(_203_));
 AND4x1_ASAP7_75t_R _461_ (.A(_203_),
    .B(_023_),
    .C(_174_),
    .D(_175_),
    .Y(_204_));
 NOR2x1_ASAP7_75t_R _462_ (.A(_202_),
    .B(_204_),
    .Y(_205_));
 AND4x1_ASAP7_75t_R _463_ (.A(_188_),
    .B(_191_),
    .C(_194_),
    .D(_205_),
    .Y(_206_));
 AND4x1_ASAP7_75t_R _464_ (.A(_170_),
    .B(_180_),
    .C(_185_),
    .D(_206_),
    .Y(_207_));
 NOR2x1_ASAP7_75t_R _465_ (.A(_169_),
    .B(_207_),
    .Y(_208_));
 OA21x2_ASAP7_75t_R _466_ (.A1(_017_),
    .A2(_135_),
    .B(_016_),
    .Y(_209_));
 XNOR2x2_ASAP7_75t_R _467_ (.A(_052_),
    .B(_209_),
    .Y(_210_));
 AND3x1_ASAP7_75t_R _468_ (.A(_089_),
    .B(_151_),
    .C(_210_),
    .Y(_211_));
 NOR3x1_ASAP7_75t_R _469_ (.A(\above[0] ),
    .B(_142_),
    .C(_150_),
    .Y(_212_));
 XNOR2x2_ASAP7_75t_R _470_ (.A(_020_),
    .B(_122_),
    .Y(_213_));
 OA21x2_ASAP7_75t_R _471_ (.A1(_149_),
    .A2(_212_),
    .B(_213_),
    .Y(_214_));
 OR2x2_ASAP7_75t_R _472_ (.A(_211_),
    .B(_214_),
    .Y(_215_));
 XNOR2x2_ASAP7_75t_R _473_ (.A(_017_),
    .B(_003_),
    .Y(_216_));
 OR3x1_ASAP7_75t_R _474_ (.A(\above[1] ),
    .B(\above[0] ),
    .C(_216_),
    .Y(_217_));
 INVx1_ASAP7_75t_R _475_ (.A(_217_),
    .Y(_218_));
 AND3x1_ASAP7_75t_R _476_ (.A(_089_),
    .B(_151_),
    .C(_218_),
    .Y(_219_));
 XNOR2x2_ASAP7_75t_R _477_ (.A(_002_),
    .B(_077_),
    .Y(_220_));
 OR3x1_ASAP7_75t_R _478_ (.A(\below[1] ),
    .B(\below[0] ),
    .C(_220_),
    .Y(_221_));
 AOI21x1_ASAP7_75t_R _479_ (.A1(_089_),
    .A2(_151_),
    .B(_221_),
    .Y(_222_));
 OR2x2_ASAP7_75t_R _480_ (.A(_219_),
    .B(_222_),
    .Y(_223_));
 OA21x2_ASAP7_75t_R _481_ (.A1(_017_),
    .A2(_172_),
    .B(_016_),
    .Y(_224_));
 OA21x2_ASAP7_75t_R _482_ (.A1(_052_),
    .A2(_224_),
    .B(_054_),
    .Y(_225_));
 XOR2x2_ASAP7_75t_R _483_ (.A(_066_),
    .B(_225_),
    .Y(_226_));
 OR3x1_ASAP7_75t_R _484_ (.A(_149_),
    .B(_212_),
    .C(_226_),
    .Y(_227_));
 OA21x2_ASAP7_75t_R _485_ (.A1(_020_),
    .A2(_112_),
    .B(_019_),
    .Y(_228_));
 XOR2x2_ASAP7_75t_R _486_ (.A(_080_),
    .B(_228_),
    .Y(_229_));
 AO21x1_ASAP7_75t_R _487_ (.A1(_089_),
    .A2(_151_),
    .B(_229_),
    .Y(_230_));
 NAND2x1_ASAP7_75t_R _488_ (.A(_227_),
    .B(_230_),
    .Y(_231_));
 AOI21x1_ASAP7_75t_R _489_ (.A1(_215_),
    .A2(_223_),
    .B(_231_),
    .Y(_232_));
 OR2x2_ASAP7_75t_R _490_ (.A(_208_),
    .B(_232_),
    .Y(_233_));
 INVx1_ASAP7_75t_R _492_ (.A(_233_),
    .Y(g1_11));
 INVx1_ASAP7_75t_R _493_ (.A(\stepped[0] ),
    .Y(net13));
 INVx1_ASAP7_75t_R _494_ (.A(_009_),
    .Y(net14));
 INVx1_ASAP7_75t_R _495_ (.A(_015_),
    .Y(net15));
 INVx1_ASAP7_75t_R _496_ (.A(_053_),
    .Y(net16));
 INVx1_ASAP7_75t_R _497_ (.A(_064_),
    .Y(net17));
 INVx1_ASAP7_75t_R _498_ (.A(_084_),
    .Y(net18));
 INVx1_ASAP7_75t_R _499_ (.A(_021_),
    .Y(net19));
 INVx1_ASAP7_75t_R _500_ (.A(_028_),
    .Y(net20));
 INVx1_ASAP7_75t_R _501_ (.A(_049_),
    .Y(net21));
 INVx1_ASAP7_75t_R _502_ (.A(_032_),
    .Y(\confidence[0] ));
 INVx1_ASAP7_75t_R _503_ (.A(_033_),
    .Y(\confidence[1] ));
 INVx1_ASAP7_75t_R _504_ (.A(net8),
    .Y(_024_));
 INVx1_ASAP7_75t_R _505_ (.A(net5),
    .Y(_078_));
 INVx1_ASAP7_75t_R _506_ (.A(net2),
    .Y(_012_));
 INVx1_ASAP7_75t_R _507_ (.A(net3),
    .Y(_075_));
 INVx1_ASAP7_75t_R _508_ (.A(net10),
    .Y(_061_));
 INVx1_ASAP7_75t_R _509_ (.A(net4),
    .Y(_018_));
 INVx1_ASAP7_75t_R _510_ (.A(net9),
    .Y(_056_));
 INVx1_ASAP7_75t_R _511_ (.A(_037_),
    .Y(_234_));
 OR4x1_ASAP7_75t_R _512_ (.A(_211_),
    .B(_214_),
    .C(_219_),
    .D(_222_),
    .Y(_235_));
 INVx1_ASAP7_75t_R _514_ (.A(net12),
    .Y(_237_));
 INVx1_ASAP7_75t_R _515_ (.A(_001_),
    .Y(_238_));
 INVx1_ASAP7_75t_R _516_ (.A(_036_),
    .Y(_239_));
 INVx1_ASAP7_75t_R _517_ (.A(_000_),
    .Y(_240_));
 AND3x1_ASAP7_75t_R _518_ (.A(_238_),
    .B(_239_),
    .C(_240_),
    .Y(_241_));
 OR3x1_ASAP7_75t_R _519_ (.A(_237_),
    .B(_004_),
    .C(_241_),
    .Y(_242_));
 AOI21x1_ASAP7_75t_R _520_ (.A1(_227_),
    .A2(_230_),
    .B(_242_),
    .Y(_243_));
 OA211x2_ASAP7_75t_R _521_ (.A1(_169_),
    .A2(_207_),
    .B(_235_),
    .C(_243_),
    .Y(_244_));
 AOI21x1_ASAP7_75t_R _523_ (.A1(_234_),
    .A2(_244_),
    .B(_000_),
    .Y(_246_));
 AND3x1_ASAP7_75t_R _524_ (.A(_234_),
    .B(_000_),
    .C(_244_),
    .Y(_247_));
 INVx1_ASAP7_75t_R _525_ (.A(net11),
    .Y(_248_));
 OA21x2_ASAP7_75t_R _527_ (.A1(_246_),
    .A2(_247_),
    .B(_248_),
    .Y(_095_));
 NAND2x1_ASAP7_75t_R _528_ (.A(_035_),
    .B(_244_),
    .Y(_250_));
 OA211x2_ASAP7_75t_R _529_ (.A1(\confidence[1] ),
    .A2(_244_),
    .B(_250_),
    .C(_248_),
    .Y(_096_));
 XNOR2x2_ASAP7_75t_R _530_ (.A(_032_),
    .B(_244_),
    .Y(_251_));
 AND2x2_ASAP7_75t_R _531_ (.A(_248_),
    .B(_251_),
    .Y(_097_));
 OAI21x1_ASAP7_75t_R _532_ (.A1(\below[1] ),
    .A2(\below[0] ),
    .B(_220_),
    .Y(_252_));
 OA211x2_ASAP7_75t_R _533_ (.A1(_149_),
    .A2(_212_),
    .B(_213_),
    .C(_252_),
    .Y(_253_));
 OAI21x1_ASAP7_75t_R _534_ (.A1(\above[1] ),
    .A2(\above[0] ),
    .B(_216_),
    .Y(_254_));
 AND4x1_ASAP7_75t_R _535_ (.A(_089_),
    .B(_151_),
    .C(_210_),
    .D(_254_),
    .Y(_255_));
 OR2x2_ASAP7_75t_R _536_ (.A(_253_),
    .B(_255_),
    .Y(_256_));
 INVx1_ASAP7_75t_R _537_ (.A(_005_),
    .Y(_257_));
 OR4x2_ASAP7_75t_R _538_ (.A(_238_),
    .B(_257_),
    .C(_240_),
    .D(_034_),
    .Y(_258_));
 AO21x1_ASAP7_75t_R _539_ (.A1(_231_),
    .A2(_256_),
    .B(_258_),
    .Y(_259_));
 OR3x2_ASAP7_75t_R _540_ (.A(_169_),
    .B(_207_),
    .C(_258_),
    .Y(_260_));
 OR4x1_ASAP7_75t_R _541_ (.A(_053_),
    .B(_064_),
    .C(_084_),
    .D(_021_),
    .Y(_261_));
 OR4x1_ASAP7_75t_R _542_ (.A(_046_),
    .B(\stepped[0] ),
    .C(_009_),
    .D(_015_),
    .Y(_262_));
 OR4x1_ASAP7_75t_R _543_ (.A(_028_),
    .B(_049_),
    .C(_261_),
    .D(_262_),
    .Y(_263_));
 INVx1_ASAP7_75t_R _544_ (.A(g1_7),
    .Y(_264_));
 AND2x2_ASAP7_75t_R _545_ (.A(do_up),
    .B(_264_),
    .Y(_265_));
 INVx1_ASAP7_75t_R _546_ (.A(do_up),
    .Y(_266_));
 NAND2x1_ASAP7_75t_R _547_ (.A(_266_),
    .B(g1_7),
    .Y(_267_));
 AND4x1_ASAP7_75t_R _548_ (.A(_053_),
    .B(_064_),
    .C(_084_),
    .D(_021_),
    .Y(_268_));
 AND4x1_ASAP7_75t_R _549_ (.A(_046_),
    .B(\stepped[0] ),
    .C(_009_),
    .D(_015_),
    .Y(_269_));
 AND4x1_ASAP7_75t_R _550_ (.A(_028_),
    .B(_049_),
    .C(_268_),
    .D(_269_),
    .Y(_270_));
 NOR2x1_ASAP7_75t_R _551_ (.A(_267_),
    .B(_270_),
    .Y(_006_));
 AOI21x1_ASAP7_75t_R _552_ (.A1(_263_),
    .A2(_265_),
    .B(_006_),
    .Y(_271_));
 AND2x2_ASAP7_75t_R _553_ (.A(_248_),
    .B(_271_),
    .Y(_272_));
 AO32x2_ASAP7_75t_R _554_ (.A1(_259_),
    .A2(_260_),
    .A3(_272_),
    .B1(_248_),
    .B2(_237_),
    .Y(_273_));
 AND3x1_ASAP7_75t_R _556_ (.A(net12),
    .B(net9),
    .C(_248_),
    .Y(_275_));
 OA211x2_ASAP7_75t_R _557_ (.A1(_169_),
    .A2(_207_),
    .B(_231_),
    .C(_256_),
    .Y(_276_));
 NOR2x1_ASAP7_75t_R _558_ (.A(_258_),
    .B(_276_),
    .Y(_277_));
 AO21x1_ASAP7_75t_R _559_ (.A1(_263_),
    .A2(_265_),
    .B(_006_),
    .Y(_278_));
 AND2x2_ASAP7_75t_R _561_ (.A(net12),
    .B(_248_),
    .Y(_280_));
 OA21x2_ASAP7_75t_R _562_ (.A1(_039_),
    .A2(_007_),
    .B(_038_),
    .Y(_281_));
 OA21x2_ASAP7_75t_R _563_ (.A1(_087_),
    .A2(_281_),
    .B(_086_),
    .Y(_282_));
 OR2x2_ASAP7_75t_R _564_ (.A(_082_),
    .B(_282_),
    .Y(_283_));
 AO21x1_ASAP7_75t_R _565_ (.A1(_081_),
    .A2(_283_),
    .B(_045_),
    .Y(_284_));
 AND3x1_ASAP7_75t_R _566_ (.A(_040_),
    .B(_044_),
    .C(_059_),
    .Y(_285_));
 AND3x1_ASAP7_75t_R _567_ (.A(_060_),
    .B(_040_),
    .C(_059_),
    .Y(_286_));
 AO221x1_ASAP7_75t_R _568_ (.A1(_040_),
    .A2(_041_),
    .B1(_284_),
    .B2(_285_),
    .C(_286_),
    .Y(_287_));
 XOR2x2_ASAP7_75t_R _569_ (.A(_094_),
    .B(_287_),
    .Y(_288_));
 AND5x1_ASAP7_75t_R _570_ (.A(_259_),
    .B(_260_),
    .C(_278_),
    .D(_280_),
    .E(_288_),
    .Y(_289_));
 AO221x2_ASAP7_75t_R _571_ (.A1(net21),
    .A2(_273_),
    .B1(_275_),
    .B2(_277_),
    .C(_289_),
    .Y(_098_));
 AND3x1_ASAP7_75t_R _572_ (.A(net12),
    .B(net8),
    .C(_248_),
    .Y(_290_));
 OA21x2_ASAP7_75t_R _573_ (.A1(\stepped[0] ),
    .A2(_068_),
    .B(_067_),
    .Y(_291_));
 OR3x1_ASAP7_75t_R _574_ (.A(_082_),
    .B(_039_),
    .C(_087_),
    .Y(_292_));
 OR2x2_ASAP7_75t_R _575_ (.A(_082_),
    .B(_038_),
    .Y(_293_));
 OA222x2_ASAP7_75t_R _576_ (.A1(_082_),
    .A2(_086_),
    .B1(_291_),
    .B2(_292_),
    .C1(_293_),
    .C2(_087_),
    .Y(_294_));
 AND3x1_ASAP7_75t_R _577_ (.A(_081_),
    .B(_044_),
    .C(_059_),
    .Y(_295_));
 AND3x1_ASAP7_75t_R _578_ (.A(_044_),
    .B(_045_),
    .C(_059_),
    .Y(_296_));
 AO221x1_ASAP7_75t_R _579_ (.A1(_060_),
    .A2(_059_),
    .B1(_294_),
    .B2(_295_),
    .C(_296_),
    .Y(_297_));
 XOR2x2_ASAP7_75t_R _580_ (.A(_041_),
    .B(_297_),
    .Y(_298_));
 AND5x1_ASAP7_75t_R _581_ (.A(_259_),
    .B(_260_),
    .C(_278_),
    .D(_280_),
    .E(_298_),
    .Y(_299_));
 AO221x2_ASAP7_75t_R _582_ (.A1(net20),
    .A2(_273_),
    .B1(_290_),
    .B2(_277_),
    .C(_299_),
    .Y(_099_));
 AND3x1_ASAP7_75t_R _583_ (.A(net12),
    .B(net7),
    .C(_248_),
    .Y(_300_));
 NAND2x1_ASAP7_75t_R _584_ (.A(_044_),
    .B(_284_),
    .Y(_301_));
 XNOR2x2_ASAP7_75t_R _585_ (.A(_060_),
    .B(_301_),
    .Y(_302_));
 AND5x1_ASAP7_75t_R _586_ (.A(_259_),
    .B(_260_),
    .C(_278_),
    .D(_280_),
    .E(_302_),
    .Y(_303_));
 AO221x2_ASAP7_75t_R _587_ (.A1(net19),
    .A2(_273_),
    .B1(_300_),
    .B2(_277_),
    .C(_303_),
    .Y(_100_));
 AND3x1_ASAP7_75t_R _588_ (.A(net12),
    .B(net6),
    .C(_248_),
    .Y(_304_));
 NAND2x1_ASAP7_75t_R _589_ (.A(_081_),
    .B(_294_),
    .Y(_305_));
 XNOR2x2_ASAP7_75t_R _590_ (.A(_045_),
    .B(_305_),
    .Y(_306_));
 AND5x1_ASAP7_75t_R _591_ (.A(_259_),
    .B(_260_),
    .C(_278_),
    .D(_280_),
    .E(_306_),
    .Y(_307_));
 AO221x2_ASAP7_75t_R _592_ (.A1(net18),
    .A2(_273_),
    .B1(_304_),
    .B2(_277_),
    .C(_307_),
    .Y(_101_));
 AND3x1_ASAP7_75t_R _593_ (.A(net12),
    .B(net5),
    .C(_248_),
    .Y(_308_));
 XOR2x2_ASAP7_75t_R _594_ (.A(_082_),
    .B(_282_),
    .Y(_309_));
 AND5x1_ASAP7_75t_R _595_ (.A(_259_),
    .B(_260_),
    .C(_278_),
    .D(_280_),
    .E(_309_),
    .Y(_310_));
 AO221x2_ASAP7_75t_R _596_ (.A1(net17),
    .A2(_273_),
    .B1(_308_),
    .B2(_277_),
    .C(_310_),
    .Y(_102_));
 AND3x1_ASAP7_75t_R _597_ (.A(net12),
    .B(net4),
    .C(_248_),
    .Y(_311_));
 OA21x2_ASAP7_75t_R _598_ (.A1(_039_),
    .A2(_291_),
    .B(_038_),
    .Y(_312_));
 XOR2x2_ASAP7_75t_R _599_ (.A(_087_),
    .B(_312_),
    .Y(_313_));
 AND5x1_ASAP7_75t_R _600_ (.A(_259_),
    .B(_260_),
    .C(_278_),
    .D(_280_),
    .E(_313_),
    .Y(_314_));
 AO221x2_ASAP7_75t_R _601_ (.A1(net16),
    .A2(_273_),
    .B1(_311_),
    .B2(_277_),
    .C(_314_),
    .Y(_103_));
 AND3x1_ASAP7_75t_R _602_ (.A(net12),
    .B(net3),
    .C(_248_),
    .Y(_315_));
 XOR2x2_ASAP7_75t_R _603_ (.A(_039_),
    .B(_007_),
    .Y(_316_));
 AND5x1_ASAP7_75t_R _604_ (.A(_259_),
    .B(_260_),
    .C(_278_),
    .D(_280_),
    .E(_316_),
    .Y(_317_));
 AO221x2_ASAP7_75t_R _605_ (.A1(net15),
    .A2(_273_),
    .B1(_315_),
    .B2(_277_),
    .C(_317_),
    .Y(_104_));
 AND3x1_ASAP7_75t_R _606_ (.A(net12),
    .B(net2),
    .C(_248_),
    .Y(_318_));
 INVx1_ASAP7_75t_R _607_ (.A(_008_),
    .Y(_319_));
 AND5x1_ASAP7_75t_R _608_ (.A(_319_),
    .B(_259_),
    .C(_260_),
    .D(_278_),
    .E(_280_),
    .Y(_320_));
 AO221x2_ASAP7_75t_R _609_ (.A1(net14),
    .A2(_273_),
    .B1(_318_),
    .B2(_277_),
    .C(_320_),
    .Y(_105_));
 NOR2x1_ASAP7_75t_R _610_ (.A(net12),
    .B(\stepped[0] ),
    .Y(_321_));
 AND3x1_ASAP7_75t_R _611_ (.A(net12),
    .B(net1),
    .C(_248_),
    .Y(_322_));
 AND4x1_ASAP7_75t_R _612_ (.A(net12),
    .B(\stepped[0] ),
    .C(_248_),
    .D(_278_),
    .Y(_323_));
 OR3x1_ASAP7_75t_R _613_ (.A(\stepped[0] ),
    .B(net11),
    .C(_278_),
    .Y(_324_));
 INVx1_ASAP7_75t_R _614_ (.A(_324_),
    .Y(_325_));
 OA211x2_ASAP7_75t_R _615_ (.A1(_323_),
    .A2(_325_),
    .B(_259_),
    .C(_260_),
    .Y(_326_));
 AO221x1_ASAP7_75t_R _616_ (.A1(_248_),
    .A2(_321_),
    .B1(_322_),
    .B2(_277_),
    .C(_326_),
    .Y(_106_));
 AND2x2_ASAP7_75t_R _617_ (.A(_237_),
    .B(_005_),
    .Y(_327_));
 AOI211x1_ASAP7_75t_R _618_ (.A1(net12),
    .A2(_233_),
    .B(_327_),
    .C(net11),
    .Y(_107_));
 INVx1_ASAP7_75t_R _619_ (.A(net6),
    .Y(_072_));
 INVx1_ASAP7_75t_R _620_ (.A(_276_),
    .Y(_088_));
 INVx1_ASAP7_75t_R _621_ (.A(net1),
    .Y(_055_));
 INVx1_ASAP7_75t_R _622_ (.A(net7),
    .Y(_069_));
 OR3x1_ASAP7_75t_R _623_ (.A(_032_),
    .B(_033_),
    .C(_000_),
    .Y(_328_));
 INVx1_ASAP7_75t_R _624_ (.A(_328_),
    .Y(_329_));
 AOI21x1_ASAP7_75t_R _625_ (.A1(_244_),
    .A2(_329_),
    .B(_001_),
    .Y(_330_));
 AND3x1_ASAP7_75t_R _626_ (.A(_001_),
    .B(_244_),
    .C(_329_),
    .Y(_331_));
 OA21x2_ASAP7_75t_R _627_ (.A1(_330_),
    .A2(_331_),
    .B(_248_),
    .Y(_108_));
 AND2x2_ASAP7_75t_R _628_ (.A(net12),
    .B(_061_),
    .Y(_332_));
 AO21x1_ASAP7_75t_R _629_ (.A1(_237_),
    .A2(_046_),
    .B(net11),
    .Y(_333_));
 OR2x2_ASAP7_75t_R _630_ (.A(_094_),
    .B(_041_),
    .Y(_334_));
 OA22x2_ASAP7_75t_R _631_ (.A1(_094_),
    .A2(_040_),
    .B1(_297_),
    .B2(_334_),
    .Y(_335_));
 NAND2x1_ASAP7_75t_R _632_ (.A(_093_),
    .B(_335_),
    .Y(_336_));
 AND4x1_ASAP7_75t_R _633_ (.A(_046_),
    .B(_266_),
    .C(g1_7),
    .D(_006_),
    .Y(_337_));
 AOI21x1_ASAP7_75t_R _634_ (.A1(net22),
    .A2(_267_),
    .B(_337_),
    .Y(_338_));
 AND4x1_ASAP7_75t_R _635_ (.A(_046_),
    .B(do_up),
    .C(_264_),
    .D(_263_),
    .Y(_339_));
 NAND2x1_ASAP7_75t_R _636_ (.A(_336_),
    .B(_339_),
    .Y(_340_));
 OR3x1_ASAP7_75t_R _637_ (.A(_046_),
    .B(do_up),
    .C(_264_),
    .Y(_341_));
 OA21x2_ASAP7_75t_R _638_ (.A1(_093_),
    .A2(_267_),
    .B(_278_),
    .Y(_342_));
 OA222x2_ASAP7_75t_R _639_ (.A1(net12),
    .A2(_271_),
    .B1(_335_),
    .B2(_341_),
    .C1(_342_),
    .C2(_046_),
    .Y(_343_));
 OA211x2_ASAP7_75t_R _640_ (.A1(_336_),
    .A2(_338_),
    .B(_340_),
    .C(_343_),
    .Y(_344_));
 OA21x2_ASAP7_75t_R _641_ (.A1(_258_),
    .A2(_276_),
    .B(_344_),
    .Y(_345_));
 AOI211x1_ASAP7_75t_R _642_ (.A1(_277_),
    .A2(_332_),
    .B(_333_),
    .C(_345_),
    .Y(_109_));
 AND3x1_ASAP7_75t_R _643_ (.A(net12),
    .B(_092_),
    .C(_091_),
    .Y(_346_));
 AOI211x1_ASAP7_75t_R _644_ (.A1(_237_),
    .A2(_004_),
    .B(net11),
    .C(_346_),
    .Y(_110_));
 FAx1_ASAP7_75t_R _645_ (.SN(_008_),
    .A(net13),
    .B(net14),
    .CI(_006_),
    .CON(_007_));
 FAx1_ASAP7_75t_R _646_ (.SN(\below[1] ),
    .A(net2),
    .B(_009_),
    .CI(_010_),
    .CON(_002_));
 FAx1_ASAP7_75t_R _647_ (.SN(\above[1] ),
    .A(_012_),
    .B(net14),
    .CI(_013_),
    .CON(_003_));
 HAxp5_ASAP7_75t_R _648_ (.A(net3),
    .B(_015_),
    .CON(_016_),
    .SN(_017_));
 HAxp5_ASAP7_75t_R _649_ (.A(net16),
    .B(_018_),
    .CON(_019_),
    .SN(_020_));
 HAxp5_ASAP7_75t_R _650_ (.A(net7),
    .B(_021_),
    .CON(_022_),
    .SN(_023_));
 HAxp5_ASAP7_75t_R _651_ (.A(net20),
    .B(_024_),
    .CON(_025_),
    .SN(_026_));
 HAxp5_ASAP7_75t_R _652_ (.A(_024_),
    .B(net20),
    .CON(_347_),
    .SN(_027_));
 HAxp5_ASAP7_75t_R _653_ (.A(net8),
    .B(_028_),
    .CON(_029_),
    .SN(_348_));
 HAxp5_ASAP7_75t_R _654_ (.A(net14),
    .B(_012_),
    .CON(_030_),
    .SN(_031_));
 HAxp5_ASAP7_75t_R _655_ (.A(_032_),
    .B(_033_),
    .CON(_034_),
    .SN(_035_));
 HAxp5_ASAP7_75t_R _656_ (.A(\confidence[0] ),
    .B(\confidence[1] ),
    .CON(_036_),
    .SN(_349_));
 HAxp5_ASAP7_75t_R _657_ (.A(\confidence[0] ),
    .B(\confidence[1] ),
    .CON(_037_),
    .SN(_350_));
 HAxp5_ASAP7_75t_R _658_ (.A(net15),
    .B(_006_),
    .CON(_038_),
    .SN(_039_));
 HAxp5_ASAP7_75t_R _659_ (.A(net20),
    .B(_006_),
    .CON(_040_),
    .SN(_041_));
 HAxp5_ASAP7_75t_R _660_ (.A(_012_),
    .B(net14),
    .CON(_351_),
    .SN(_042_));
 HAxp5_ASAP7_75t_R _661_ (.A(net2),
    .B(_009_),
    .CON(_043_),
    .SN(_352_));
 HAxp5_ASAP7_75t_R _662_ (.A(net18),
    .B(_006_),
    .CON(_044_),
    .SN(_045_));
 HAxp5_ASAP7_75t_R _663_ (.A(net10),
    .B(_046_),
    .CON(_047_),
    .SN(_048_));
 HAxp5_ASAP7_75t_R _664_ (.A(net9),
    .B(_049_),
    .CON(_050_),
    .SN(_051_));
 HAxp5_ASAP7_75t_R _665_ (.A(_018_),
    .B(net16),
    .CON(_353_),
    .SN(_052_));
 HAxp5_ASAP7_75t_R _666_ (.A(net4),
    .B(_053_),
    .CON(_054_),
    .SN(_354_));
 HAxp5_ASAP7_75t_R _667_ (.A(_055_),
    .B(net13),
    .CON(_014_),
    .SN(\above[0] ));
 HAxp5_ASAP7_75t_R _668_ (.A(_056_),
    .B(net21),
    .CON(_057_),
    .SN(_058_));
 HAxp5_ASAP7_75t_R _669_ (.A(net19),
    .B(_006_),
    .CON(_059_),
    .SN(_060_));
 HAxp5_ASAP7_75t_R _670_ (.A(_061_),
    .B(net22),
    .CON(_062_),
    .SN(_063_));
 HAxp5_ASAP7_75t_R _671_ (.A(net5),
    .B(_064_),
    .CON(_065_),
    .SN(_066_));
 HAxp5_ASAP7_75t_R _672_ (.A(net14),
    .B(_006_),
    .CON(_067_),
    .SN(_068_));
 HAxp5_ASAP7_75t_R _673_ (.A(_069_),
    .B(net19),
    .CON(_070_),
    .SN(_071_));
 HAxp5_ASAP7_75t_R _674_ (.A(net18),
    .B(_072_),
    .CON(_073_),
    .SN(_074_));
 HAxp5_ASAP7_75t_R _675_ (.A(_075_),
    .B(net15),
    .CON(_076_),
    .SN(_077_));
 HAxp5_ASAP7_75t_R _676_ (.A(_078_),
    .B(net17),
    .CON(_079_),
    .SN(_080_));
 HAxp5_ASAP7_75t_R _677_ (.A(net17),
    .B(_006_),
    .CON(_081_),
    .SN(_082_));
 HAxp5_ASAP7_75t_R _678_ (.A(_072_),
    .B(net18),
    .CON(_355_),
    .SN(_083_));
 HAxp5_ASAP7_75t_R _679_ (.A(net6),
    .B(_084_),
    .CON(_085_),
    .SN(_356_));
 HAxp5_ASAP7_75t_R _680_ (.A(_055_),
    .B(net13),
    .CON(_357_),
    .SN(\below[0] ));
 HAxp5_ASAP7_75t_R _681_ (.A(net1),
    .B(\stepped[0] ),
    .CON(_011_),
    .SN(_358_));
 HAxp5_ASAP7_75t_R _682_ (.A(net16),
    .B(_006_),
    .CON(_086_),
    .SN(_087_));
 HAxp5_ASAP7_75t_R _683_ (.A(_088_),
    .B(_149_),
    .CON(_359_),
    .SN(g1_7));
 HAxp5_ASAP7_75t_R _684_ (.A(_233_),
    .B(_149_),
    .CON(_360_),
    .SN(do_up));
 HAxp5_ASAP7_75t_R _685_ (.A(g1_11),
    .B(_149_),
    .CON(_091_),
    .SN(_361_));
 HAxp5_ASAP7_75t_R _686_ (.A(g1_11),
    .B(_089_),
    .CON(_092_),
    .SN(_362_));
 HAxp5_ASAP7_75t_R _687_ (.A(net21),
    .B(_006_),
    .CON(_093_),
    .SN(_094_));
 DFFHQNx1_ASAP7_75t_R \candidate[0]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_106_),
    .QN(\stepped[0] ));
 DFFHQNx1_ASAP7_75t_R \candidate[1]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_105_),
    .QN(_009_));
 DFFHQNx1_ASAP7_75t_R \candidate[2]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_104_),
    .QN(_015_));
 DFFHQNx1_ASAP7_75t_R \candidate[3]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_103_),
    .QN(_053_));
 DFFHQNx1_ASAP7_75t_R \candidate[4]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_102_),
    .QN(_064_));
 DFFHQNx1_ASAP7_75t_R \candidate[5]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_101_),
    .QN(_084_));
 DFFHQNx1_ASAP7_75t_R \candidate[6]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_100_),
    .QN(_021_));
 DFFHQNx1_ASAP7_75t_R \candidate[7]$_SDFFE_PP0P_  (.CLK(clknet_1_0__leaf_clk),
    .D(_099_),
    .QN(_028_));
 DFFHQNx1_ASAP7_75t_R \candidate[8]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_098_),
    .QN(_049_));
 DFFHQNx1_ASAP7_75t_R \candidate[9]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_109_),
    .QN(_046_));
 BUFx2_ASAP7_75t_R clkbuf_0_clk (.A(clk),
    .Y(clknet_0_clk));
 BUFx2_ASAP7_75t_R clkbuf_1_0__f_clk (.A(clknet_0_clk),
    .Y(clknet_1_0__leaf_clk));
 BUFx2_ASAP7_75t_R clkbuf_1_1__f_clk (.A(clknet_0_clk),
    .Y(clknet_1_1__leaf_clk));
 DFFHQNx1_ASAP7_75t_R \confidence[0]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_097_),
    .QN(_032_));
 DFFHQNx1_ASAP7_75t_R \confidence[1]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_096_),
    .QN(_033_));
 DFFHQNx1_ASAP7_75t_R \confidence[2]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_095_),
    .QN(_000_));
 DFFHQNx1_ASAP7_75t_R \confidence[3]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_108_),
    .QN(_001_));
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
    .D(_107_),
    .QN(_005_));
 DFFHQNx1_ASAP7_75t_R \state[1]$_SDFFE_PP0P_  (.CLK(clknet_1_1__leaf_clk),
    .D(_110_),
    .QN(_004_));
endmodule
