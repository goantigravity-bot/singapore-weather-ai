export const LABELS = {
    common: {
        loading: "Loading...",
        error: "Error",
        backToHome: "Back to Home",
        refresh: "Refresh",
        view: "View",
        close: "Close"
    },
    app: {
        title: "Singapore Weather AI",
        trainingMonitor: "Training Monitor",
        searchPlaceholder: "Enter location (e.g. Sentosa)...",
        menu: "Menu",
        popularPlaces: "Popular Places",
        settings: "Settings",
        about: "About"
    },
    monitor: {
        // ... (existing monitor labels)
        title: "System Monitor Dashboard",
        autoRefresh: "Auto-refresh: 5s",
        viewLogs: "View Logs",
        lastUpdate: "Last Update",
        tabs: {
            download: {
                label: "Downloads",
                completedDays: "Completed Days",
                totalFiles: "Total Files",
                currentDate: "Current Date",
                overallProgress: "Overall Progress",
                dailyDetails: "Daily Download Details",
                table: {
                    status: "Status",
                    date: "Date",
                    satelliteData: "Satellite Data",
                    neaData: "NEA Data"
                }
            },
            training: {
                label: "Training",
                currentDate: "Current Date",
                completedBatches: "Completed Batches",
                totalEpochs: "Total Epochs",
                history: "Training History",
                phases: {
                    pending: "Pending",
                    running: "Running",
                    completed: "Completed",
                    error: "Error"
                },
                table: {
                    status: "Status",
                    date: "Date",
                    range: "Date Range",
                    duration: "Duration",
                    mae: "MAE",
                    rmse: "RMSE"
                }
            },
            api: {
                label: "API Status",
                modelSynced: "Model Synced",
                sensorData: "Sensor Data",
                synced: "Synced",
                pending: "Pending",
                lastSyncTime: "Last Sync Time",
                serviceStatus: "Service Status",
                operational: "Operational",
                statusPrefix: "Status: "
            }
        },
        logs: {
            title: {
                download: "Download Logs",
                training: "Training Logs",
                api: "API Sync Logs"
            },
            noLogs: "No logs available",
            loading: "Loading Logs..."
        }
    },
    settings: {
        title: "Configuration",
        description: "Select which weather metrics to display on the forecast panel.",
        mapOptions: "Map Display Options",
        visible: "Visible",
        hidden: "Hidden",
        metrics: {
            rain: "Rainfall Prediction",
            temp: "Temperature",
            hum: "Humidity",
            pm25: "PM2.5 (Air Quality)"
        },
        toggles: {
            triangle: "Interpolation Triangle",
            stations: "Weather Station Markers"
        },
        integration: {
            title: "Integration",
            geocodingProvider: "Geocoding Provider",
            nominatim: "Nominatim",
            nominatimDesc: "OSM Global",
            onemap: "OneMap",
            onemapDesc: "SLA Singapore"
        }
    },
    stats: {
        title: "Popular Places",
        loading: "Loading statistics...",
        noHistory: "No search history yet.",
        searches: "searches",
        view: "View",
        footer: "Top 6 most searched locations"
    },
    smartResult: {
        query: "Query",
        time: "Time",
        showDetails: "Show Details",
        hideDetails: "Hide Details",
        point: "Pt",
        dry: "Dry"
    }
};
