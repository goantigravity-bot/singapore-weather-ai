Himawari Wild Fire product

Updated Dec. 7, 2022: Add file name rule for Himawari-9


1. Description



	This product provides the location and the fire radiative power (FRP) of hot spots retrieved from the IR imageries obtained with the Himawari-8 satellite. The retrieval algorithm was developed at JAXA/EORC. Details on the algorithm is being prepared for publication with validation results.



2. Version : 1.00 (January 2020)



3. Algorithm : 



	Hotspots are detected based on the normalized deviation of the 3.9 um brightness temperature from the background temperature determined from the 10.8 um brightness temperatures at surrounding 11x11 grids. FRP is determined by performing the Bi-spectral method on 2.3 um and 3.9 um data. 



4. Data coverage : full disk (60N-60S, 80E-160W)



5. Spatial resolution : 0.02 x 0.02 degrees for latitude and longitude (2 km x 2 km at nadir)



6. Time resolution : 10 min. (Level 2)



7. Data : Location and the fire radiative power (FRP)



8. Format : Comma-separated values in a text format.



8-1. File name



 Hnn_YYYYMMDD_hhmm_L2WLFVER_FLDK.xxxxx_yyyyy.csv

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



8-2. Header

	Each data has two header lines which are denoted by the # at the beginning of the line. The first header line provides the acquisition time and the processed time in UTC, and the second header line provides the short names for the data in the main body.



8-3. Main body

	The main body provides the retrieved data listed below in a CSV format.



 ID			Fire grid ID

 Date			Year, Month, Day, and Time (hhmn) (UTC)

 Lat			Latitude of the center of the grid

 Lon			Longitude of the center of the grid

 Area			Area of the grid (km^2)

 Volcano		The total number of volcanos within the 3x3 grids

 Level			Fire level (1: cold, 2: smoldering, 3: flaming)

 Reliability level	1: low, 3: normal, 5: high 

 FRP			Fire radiative power (Wm^-2)

 QF			Quality flag with FRP (0: normal, 1: 3.9 um is saturated, 2: low confidence)

 HC			Hot center of the fire cluster (denoted by ID)





Note 1) The fire level is given based on the fire temperature which is determined with the Bi-spectral method; however, the fire temperature and the fraction of the fire are not provided because of insufficient validations of them.



Note 2) The reliability level is given depending on the situations with the detection of the fire such as sun glint, solar angle, spatial variabilities of the brightness temperatures, and so on. Frequently detected host spots, which likely originate from economic or other human activities, will be rated as low reliability.



Note 3) A fire cluster is defined by fire grids contacting to each other. The hot center (HC) of a fire cluster denotes the grid with the highest fire temperature in the cluster; which is usually different from the grid with the largest FRP. The total FRP from a fire cluster will be derived by the summation of Area*FRP for each grid in the cluster: grids with the same HC.





