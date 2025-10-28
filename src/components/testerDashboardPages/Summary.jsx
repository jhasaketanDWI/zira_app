import React, { useState, useEffect, useRef } from 'react'
import { Filter, CheckCircle, FileText, Clock, Calendar, User, ChevronDown, Search } from "lucide-react";

const Summary = () => {
    const [isFilterOpen, setIsFilterOpen] = useState(false);
    const [selectedFilters, setSelectedFilters] = useState({
        assignee: false,
        created: false,
        dueDate: false,
        parent: false,
        priority: false,
        status: false,
        updated: false,
        workType: false,
    });
    
    const [summaryData, setSummaryData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const filterRef = useRef(null);

    const filterOptions = [
        { key: 'assignee', label: 'Assignee' },
        { key: 'created', label: 'Created' },
        { key: 'dueDate', label: 'Due date' },
        { key: 'parent', label: 'Parent' },
        { key: 'priority', label: 'Priority' },
        { key: 'status', label: 'Status' },
        { key: 'updated', label: 'Updated' },
        { key: 'workType', label: 'Work type' },
    ];

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (filterRef.current && !filterRef.current.contains(event.target)) {
                setIsFilterOpen(false);
            }
        };

        if (isFilterOpen) {
            document.addEventListener('mousedown', handleClickOutside);
        }

        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, [isFilterOpen]);

    const fetchSummaryData = async () => {
        // Get active project ID from localStorage
        const activeProjectId = localStorage.getItem("activeProjectId");
        
        if (!activeProjectId) {
            setError('No active project selected. Please select a project first.');
            setLoading(false);
            return;
        }

        try {
            setLoading(true);
            setError(null);
            
            const authToken = localStorage.getItem('authToken');
            
            if (!authToken) {
                setError('Please login to view summary data');
                setLoading(false);
                return;
            }

            console.log('Fetching summary for project:', activeProjectId);

            const response = await fetch(`http://127.0.0.1:8000/api/projects/${activeProjectId}/summary/`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${authToken}`
                },
            });

            if (response.status === 401) {
                setError('Session expired. Please login again');
                setLoading(false);
                return;
            }

            if (response.status === 403) {
                setError('You do not have permission to view this project summary');
                setLoading(false);
                return;
            }

            if (!response.ok) {
                throw new Error(`API request failed with status ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Summary API response:', data);
            
            setSummaryData(data);
            
        } catch (err) {
            setError(err.message);
            console.error('Error fetching summary data:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchSummaryData();
    }, []);

    // Listen for project changes
    useEffect(() => {
        const handleStorageChange = (e) => {
            if (e.key === 'activeProjectId') {
                console.log('Active project changed, refetching summary...');
                fetchSummaryData();
            }
        };

        window.addEventListener('storage', handleStorageChange);
        
        return () => {
            window.removeEventListener('storage', handleStorageChange);
        };
    }, []);

    const handleFilterToggle = (filterKey) => {
        setSelectedFilters(prev => ({
            ...prev,
            [filterKey]: !prev[filterKey]
        }));
    };

    const getSummaryData = () => {
        if (!summaryData) {
            return {
                completed: 0,
                created: 0,
                updated: 0,
                dueSoon: 0,
                totalWorkItems: 0,
                todoCount: 0,
                inProgressCount: 0,
                doneCount: 0,
                recentActivities: []
            };
        }

        const summaryCards = summaryData.summary_cards || {};
        const statusOverview = summaryData.status_overview || {};
        const recentActivity = summaryData.recent_activity || [];

        let todoCount = 0;
        let inProgressCount = 0;
        let doneCount = 0;

        if (statusOverview.breakdown) {
            statusOverview.breakdown.forEach(item => {
                if (item.status__title === 'To Do') {
                    todoCount = item.count;
                } else if (item.status__title === 'In Progress') {
                    inProgressCount = item.count;
                } else if (item.status__title === 'Done') {
                    doneCount = item.count;
                }
            });
        }

        let formattedActivities = recentActivity.map(activity => ({
            user: activity.user_email || 'Unknown User',
            action: getActionText(activity.action_type, activity.details),
            task: activity.task_title || 'Unknown Task',
            timestamp: activity.created_at,
            actionType: activity.action_type
        }));

        if (Object.values(selectedFilters).some(v => v)) {
            formattedActivities = formattedActivities.filter(activity => {
                if (selectedFilters.created && activity.actionType !== 'CREATE') return false;
                if (selectedFilters.updated && activity.actionType !== 'UPDATE') return false;
                if (selectedFilters.status && activity.actionType !== 'STATUS_CHANGE') return false;
                return true;
            });
        }

        formattedActivities = formattedActivities.slice(0, 5);

        return {
            completed: summaryCards.completed || 0,
            created: summaryCards.created || 0,
            updated: summaryCards.updated || 0,
            dueSoon: summaryCards.due_soon || 0,
            totalWorkItems: statusOverview.total || 0,
            todoCount: todoCount,
            inProgressCount: inProgressCount,
            doneCount: doneCount,
            recentActivities: formattedActivities
        };
    };

    const getActionText = (actionType, details) => {
        switch (actionType) {
            case 'CREATE':
                return 'created';
            case 'UPDATE':
                return 'updated';
            case 'DELETE':
                return 'deleted';
            case 'STATUS_CHANGE':
                return 'changed status of';
            case 'ASSIGNEE_CHANGE':
                return 'reassigned';
            default:
                return 'modified';
        }
    };

    const formatDate = (dateString) => {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', { 
            weekday: 'long', 
            year: 'numeric', 
            month: 'long', 
            day: 'numeric' 
        });
    };

    const formatRelativeTime = (dateString) => {
        if (!dateString) return '';
        const date = new Date(dateString);
        const now = new Date();
        const diffInSeconds = Math.floor((now - date) / 1000);
        
        if (diffInSeconds < 60) return 'just now';
        if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)} minutes ago`;
        if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)} hours ago`;
        if (diffInSeconds < 604800) return `${Math.floor(diffInSeconds / 86400)} days ago`;
        
        return formatDate(dateString);
    };

    const data = getSummaryData();

    const total = data.todoCount + data.inProgressCount + data.doneCount;
    const todoPercentage = total > 0 ? (data.todoCount / total) : 0.33;
    const inProgressPercentage = total > 0 ? (data.inProgressCount / total) : 0.33;
    const donePercentage = total > 0 ? (data.doneCount / total) : 0.34;

    if (loading) {
        return (
            <div className="flex-1 flex flex-col bg-gradient-to-br from-purple-300 via-purple-100 to-purple-50 p-6">
                <div className="flex items-center justify-center h-64">
                    <div className="text-lg text-gray-600">Loading summary data...</div>
                </div>
            </div>
        );
    }

    return (
        <div className="flex-1 flex flex-col bg-gradient-to-br from-purple-300 via-purple-100 to-purple-50 p-6">
            {error && (
                <div className="mb-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
                    <div className="flex justify-between items-center">
                        <div>
                            <strong>Error:</strong> {error}
                        </div>
                        <button 
                            onClick={fetchSummaryData}
                            className="ml-4 px-4 py-2 bg-red-600 text-white rounded text-sm hover:bg-red-700"
                        >
                            Retry
                        </button>
                    </div>
                </div>
            )}

            <div className="relative mb-6" ref={filterRef}>
                <button 
                    className="flex items-center justify-center text-gray-700 text-sm w-[90px] h-[43px] px-[10px] py-[10px] gap-[8px] border border-black rounded-[10px] bg-white/25 hover:bg-white/50 opacity-100"
                    onClick={() => setIsFilterOpen(!isFilterOpen)}
                >
                    <Filter className="w-4 h-4" />
                    Filter
                    {Object.values(selectedFilters).some(v => v) && (
                        <span className="ml-1 w-2 h-2 bg-purple-600 rounded-full"></span>
                    )}
                    <ChevronDown className={`w-4 h-4 transition-transform ${isFilterOpen ? 'rotate-180' : ''}`} />
                </button>

                {isFilterOpen && (
                    <div className="absolute top-full left-0 mt-2 w-80 bg-white rounded-lg shadow-lg border border-gray-200 z-10">
                        <div className="p-4">
                            <div className="relative mb-4">
                                <Search className="w-4 h-4 absolute left-3 top-3 text-gray-400" />
                                <input
                                    type="text"
                                    placeholder="Search more filters"
                                    className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                                />
                            </div>

                            <div className="space-y-0.5">
                                {filterOptions.map((option) => (
                                    <label key={option.key} className="flex items-center space-x-3 cursor-pointer hover:bg-purple-50 p-2 rounded">
                                        <input
                                            type="checkbox"
                                            checked={selectedFilters[option.key]}
                                            onChange={() => handleFilterToggle(option.key)}
                                            className="w-4 h-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500"
                                        />
                                        <span className="text-sm text-gray-700">{option.label}</span>
                                    </label>
                                ))}
                            </div>

                            {Object.values(selectedFilters).some(v => v) && (
                                <div className="mt-4 pt-4 border-t border-gray-200">
                                    <button
                                        onClick={() => setSelectedFilters({
                                            assignee: false,
                                            created: false,
                                            dueDate: false,
                                            parent: false,
                                            priority: false,
                                            status: false,
                                            updated: false,
                                            workType: false,
                                        })}
                                        className="w-full px-4 py-2 text-sm text-purple-600 hover:bg-purple-50 rounded-md font-medium"
                                    >
                                        Clear all filters
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>

            <div className="grid grid-cols-4 gap-4 mb-8">
                <div className="bg-purple-100 p-4 rounded-lg shadow border border-purple-200 flex items-center space-x-3">
                    <div className="bg-purple-200 p-2 rounded">
                        <CheckCircle className="w-6 h-6 text-purple-700" />
                    </div>
                    <div>
                        <div className="text-lg font-semibold">{data.completed} completed</div>
                        <div className="text-sm text-gray-500">in the last 7 days</div>
                    </div>
                </div>

                <div className="bg-purple-100 p-4 rounded-lg shadow border border-purple-200 flex items-center space-x-3">
                    <div className="bg-purple-200 p-2 rounded">
                        <FileText className="w-6 h-6 text-purple-700" />
                    </div>
                    <div>
                        <div className="text-lg font-semibold">{data.created} created</div>
                        <div className="text-sm text-gray-500">in the last 7 days</div>
                    </div>
                </div>

                <div className="bg-purple-100 p-4 rounded-lg shadow border border-purple-200 flex items-center space-x-3">
                    <div className="bg-purple-200 p-2 rounded">
                        <Clock className="w-6 h-6 text-purple-700" />
                    </div>
                    <div>
                        <div className="text-lg font-semibold">{data.updated} updated</div>
                        <div className="text-sm text-gray-500">in the last 7 days</div>
                    </div>
                </div>

                <div className="bg-purple-100 p-4 rounded-lg shadow border border-purple-200 flex items-center space-x-3">
                    <div className="bg-purple-200 p-2 rounded">
                        <Calendar className="w-6 h-6 text-purple-700" />
                    </div>
                    <div>
                        <div className="text-lg font-semibold">{data.dueSoon} due soon</div>
                        <div className="text-sm text-gray-500">in the next 3 days</div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-6">
                <div className="bg-purple-100 p-6 rounded-lg shadow border border-purple-200">
                    <h3 className="text-lg font-medium mb-1">Status overview</h3>
                    <p className="text-sm text-gray-600 mb-6">
                        Get a snapshot of the status of your work items
                    </p>

                    <div className="flex items-center justify-center mb-6">
                        <div className="relative w-48 h-48">
                            <svg className="w-48 h-48 transform -rotate-90" viewBox="0 0 160 160">
                                <circle cx="80" cy="80" r="60" stroke="#e5e7eb" strokeWidth="20" fill="none" />
                                <circle cx="80" cy="80" r="60" stroke="#22c55e" strokeWidth="20" fill="none" strokeDasharray={`${todoPercentage * 2 * Math.PI * 60} ${2 * Math.PI * 60}`} />
                                <circle cx="80" cy="80" r="60" stroke="#60a5fa" strokeWidth="20" fill="none" strokeDasharray={`${inProgressPercentage * 2 * Math.PI * 60} ${2 * Math.PI * 60}`} strokeDashoffset={`-${todoPercentage * 2 * Math.PI * 60}`} />
                                <circle cx="80" cy="80" r="60" stroke="#8b5cf6" strokeWidth="20" fill="none" strokeDasharray={`${donePercentage * 2 * Math.PI * 60} ${2 * Math.PI * 60}`} strokeDashoffset={`-${(todoPercentage + inProgressPercentage) * 2 * Math.PI * 60}`} />
                            </svg>
                            
                            <div className="absolute inset-0 flex items-center justify-center">
                                <div className="text-center">
                                    <div className="text-2xl font-semibold">{data.totalWorkItems}</div>
                                    <div className="text-sm text-gray-600">Total work items</div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="space-y-2">
                        <div className="flex items-center">
                            <div className="w-3 h-3 rounded-full mr-2" style={{ backgroundColor: "#22c55e" }}></div>
                            <span className="text-sm text-gray-600">To Do: {data.todoCount}</span>
                        </div>
                        <div className="flex items-center">
                            <div className="w-3 h-3 rounded-full mr-2" style={{ backgroundColor: "#60a5fa" }}></div>
                            <span className="text-sm text-gray-600">In Progress: {data.inProgressCount}</span>
                        </div>
                        <div className="flex items-center">
                            <div className="w-3 h-3 rounded-full mr-2" style={{ backgroundColor: "#8b5cf6" }}></div>
                            <span className="text-sm text-gray-600">Done: {data.doneCount}</span>
                        </div>
                    </div>
                </div>

                <div className="bg-purple-100 p-6 rounded-lg shadow border border-purple-200">
                    <div className="flex items-center justify-between mb-1">
                        <h3 className="text-lg font-medium">Recent activity</h3>
                        {Object.values(selectedFilters).some(v => v) && (
                            <span className="text-xs bg-purple-200 text-purple-700 px-2 py-1 rounded-full">
                                Filtered
                            </span>
                        )}
                    </div>
                    <p className="text-sm text-gray-600 mb-4">
                        Latest 5 changes across the project
                    </p>
                    
                    {data.recentActivities.length > 0 ? (
                        <div className="space-y-4">
                            {data.recentActivities.map((activity, index) => (
                                <div key={index} className="flex items-start">
                                    <div className="w-8 h-8 bg-purple-500 rounded-full flex items-center justify-center mr-3 mt-0.5">
                                        <span className="text-white text-sm font-medium">
                                            {activity.user.charAt(0).toUpperCase()}
                                        </span>
                                    </div>
                                    <div className="flex-1">
                                        <div className="flex items-center flex-wrap gap-1 text-sm">
                                            <span className="font-medium">{activity.user}</span>
                                            <span className="text-gray-600">{activity.action}</span>
                                            <span className="inline-flex items-center bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs font-medium">
                                                <CheckCircle className="w-3 h-3 text-blue-800 mr-1" />
                                                {activity.task}
                                            </span>
                                        </div>
                                        <div className="text-xs text-gray-500 mt-1">
                                            {formatRelativeTime(activity.timestamp)}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="text-center py-8 text-gray-500">
                            <p>No recent activity</p>
                            {Object.values(selectedFilters).some(v => v) && (
                                <p className="text-xs mt-2">Try adjusting your filters</p>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}

export default Summary;
