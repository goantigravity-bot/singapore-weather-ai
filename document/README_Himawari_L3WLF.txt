Himawari wildfire Level3

Updated Dec. 7, 2022: Add filename rule for Himawari-9

1 Hourly

  File Name :
 
  Hnn_YYYYMMDD_hhmm_L3WLFVER_FLDK.xxxxx_yyyyy.csv

   nn: 2-digit number of the Himawari satellite
     08: Himawari-8
     09: Himawari-9
   YYYY: 4-digit year of observation start time (timeline)
   MM: 2-digit month of timeline
   DD: 2-digit day of timeline
   hh: 2-digit hour of timeline
   mm: 2-digit minutes of timeline
   VER: version
   xxxxx: pixel number
   yyyyy: line number 

  Format :
 
  year, month, day,  hour, lat, lon, FRP (mean), FRP (max), confidence level, N

  year, month, day, hour : date and hour (UTC)
  FRP(mean) : Hourly mean FRP of detected wild fire (MW)
  FRP(max) : Hourly max FRP (MW)
  confidence level: mean confidence level (<=5.)
  N: the total number of the detection (1<=N<=6)


2 Daily, Monthly

  File Name :

  Hnn_YYYYMMDD_0000_aaWLFVER_FLDK.xxxxx_yyyyy.csv

   nn: 2-digit number of the Himawari satellite
     08: Himawari-8
     09: Himawari-9
   YYYY: 4-digit year of observation start time (timeline)
   MM: 2-digit month of timeline
   DD: 2-digit day of timeline
       * "01" for monthly data)
   aa: 2-digit average period
       1D: daily
       1M: monthly
   VER: version
   xxxxx: pixel number
   yyyyy: line number 

  Format :
 
  Daily   : year, month, day,  lat, lon, FRP (mean), FRP (max), N
  Monthly : year, month,  lat, lon, FRP (mean), N


  year, month, day : year, month, day
  FRP(mean): Daily/monthly mean FRP of detected wild fire (MW)
  FRP(max): Daily max FRP (MW)
  N: the total number of the detection


Note 1) FRP denotes the fire radiative power per each grid.


Note 2) Daily/monthly statistics are determined from hourly statistics, its mean confidence level >= 2.5.


Note 3) Total fire radiative energy (FRE) per each grid is estimated by FRP(mean)*N*10min*60sec.


