import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Users, X, AlertTriangle, Loader2, ShieldCheck, CheckSquare, Square } from 'lucide-react';

// Custom hook to detect clicks outside of a component to close the dropdown
const useClickOutside = (ref, handler) => {
    useEffect(() => {
        const listener = (event) => {
            if (!ref.current || ref.current.contains(event.target)) {
                return;
            }
            handler(event);
        };
        document.addEventListener('mousedown', listener);
        document.addEventListener('touchstart', listener);
        return () => {
            document.removeEventListener('mousedown', listener);
            document.removeEventListener('touchstart', listener);
        };
    }, [ref, handler]);
};

// --- NEW UNIFIED SEARCHABLE DROPDOWN COMPONENT ---
const UnifiedSearchableDropdown = ({ allMembers, selections, onSelect }) => {
    const [searchTerm, setSearchTerm] = useState('');
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef(null);
    useClickOutside(dropdownRef, () => setIsOpen(false));

    // Filter members based on search term
    const filteredMembers = allMembers.filter(member =>
        `${member.first_name} ${member.last_name}`.toLowerCase().includes(searchTerm.toLowerCase())
    );

    // Get a flat list of all currently selected members
    const getSelectedMembers = () => {
        const selectedDevs = allMembers.filter(m => m.role === 'developers' && selections.developers.includes(m.id));
        const selectedTesters = allMembers.filter(m => m.role === 'testers' && selections.testers.includes(m.id));
        const selectedManagers = allMembers.filter(m => m.role === 'managers' && selections.managers.includes(m.id));
        return [...selectedDevs, ...selectedTesters, ...selectedManagers];
    };

    return (
        <div className="flex-1" ref={dropdownRef}>
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
                <Users className="mr-2 h-5 w-5 text-indigo-700" />
                Assign Team Members
            </h3>
            <div className="relative">
                <div 
                    onClick={() => setIsOpen(prev => !prev)} 
                    className="bg-white/60 rounded-lg p-2 flex flex-wrap gap-2 items-center cursor-text min-h-[44px]"
                >
                    {/* Display selected members as tags */}
                    {getSelectedMembers().map(member => (
                        <span key={member.id} className="bg-indigo-600 text-white text-xs font-medium px-2 py-1 rounded-full flex items-center">
                            {member.first_name}
                            <X onClick={(e) => { e.stopPropagation(); onSelect(member, member.role); }} className="ml-1.5 h-3 w-3 cursor-pointer hover:text-gray-300" />
                        </span>
                    ))}
                    <input
                        type="text"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        onFocus={() => setIsOpen(true)}
                        placeholder="Search by name..."
                        className="flex-grow bg-transparent outline-none text-gray-900 placeholder-gray-700 text-sm p-1"
                    />
                </div>

                {/* Dropdown list */}
                {isOpen && (
                    <div className="absolute top-full mt-2 w-full bg-white/95 backdrop-blur-md rounded-lg shadow-xl z-10 max-h-60 overflow-y-auto">
                        {filteredMembers.length > 0 ? filteredMembers.map(member => {
                            const isSelected = selections[member.role]?.includes(member.id);
                            return (
                                <div key={member.id} onClick={() => onSelect(member, member.role)} className={`flex items-center justify-between p-3 cursor-pointer text-gray-900 hover:bg-indigo-100 transition-colors ${isSelected ? 'font-semibold' : ''}`}>
                                    <span>{member.first_name} {member.last_name} <span className="text-gray-500 text-xs capitalize">({member.role.slice(0, -1)})</span></span>
                                    {isSelected ? <CheckSquare className="h-5 w-5 text-indigo-600" /> : <Square className="h-5 w-5 text-gray-400" />}
                                </div>
                            );
                        }) : <p className="text-sm text-gray-700 p-3">No members found matching your search.</p>}
                    </div>
                )}
            </div>
        </div>
    );
};


const ManageTeamModal = ({ project, onClose }) => {
    const [assignedMembers, setAssignedMembers] = useState([]);
    // --- NEW: A single state for all available members ---
    const [allAvailableMembers, setAllAvailableMembers] = useState([]);
    const [selections, setSelections] = useState({ developers: [], testers: [], managers: [] });
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState('');
    const [showWarning, setShowWarning] = useState(false);

    // --- UPDATED: fetchData now combines all available members into one list ---
    const fetchData = useCallback(async () => {
        setLoading(true);
        setError('');
        const authToken = localStorage.getItem('authToken');
        try {
            const responses = await Promise.all([
                fetch(`http://localhost:8000/api/projects/${project.id}/members/`, { headers: { 'Authorization': `Bearer ${authToken}` } }),
                fetch(`http://localhost:8000/api/projects/${project.id}/available-members/developer/`, { headers: { 'Authorization': `Bearer ${authToken}` } }),
                fetch(`http://localhost:8000/api/projects/${project.id}/available-members/tester/`, { headers: { 'Authorization': `Bearer ${authToken}` } }),
                fetch(`http://localhost:8000/api/projects/${project.id}/available-members/manager/`, { headers: { 'Authorization': `Bearer ${authToken}` } }),
            ]);
            for (const res of responses) {
                if (!res.ok) throw new Error('Failed to fetch some team data. Please check API endpoints.');
            }
            const [assigned, devs, testers, managers] = await Promise.all(responses.map(res => res.json()));
            
            setAssignedMembers(assigned.results || assigned);

            // Combine all available members into a single array, tagging each with their role
            const combined = [
                ...(devs || []).map(d => ({ ...d, role: 'developers' })),
                ...(testers || []).map(t => ({ ...t, role: 'testers' })),
                ...(managers || []).map(m => ({ ...m, role: 'managers' })),
            ];
            setAllAvailableMembers(combined);

        } catch (err) {
            setError(err.message || 'Could not load team data.');
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [project.id]);

    useEffect(() => { fetchData(); }, [fetchData]);

    // This function's logic remains the same
    const handleSelect = (user, role) => {
        setShowWarning(false);
        const otherRoles = Object.keys(selections).filter(r => r !== role);
        let warningNeeded = false;
        
        otherRoles.forEach(r => {
            if (selections[r].length > 0) warningNeeded = true;
        });
        
        if (warningNeeded) setShowWarning(true);
        
        setSelections(prev => {
            const newSelections = { developers: [], testers: [], managers: [] };
            const currentRoleSelection = prev[role].includes(user.id)
                ? prev[role].filter(id => id !== user.id)
                : [...prev[role], user.id];
            newSelections[role] = currentRoleSelection;
            return newSelections;
        });
    };

    // This function's logic remains the same
    const handleSubmit = async () => {
        const roleToSubmit = Object.keys(selections).find(role => selections[role].length > 0);
        if (!roleToSubmit) return;
        
        setSubmitting(true);
        setError('');
        const authToken = localStorage.getItem('authToken');
        
        const roleApiMap = {
            developers: 'developer',
            testers: 'tester',
            managers: 'MANAGER'
        };

        try {
            const response = await fetch(`http://localhost:8000/api/projects/${project.id}/members/bulk-assign/${roleApiMap[roleToSubmit]}/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` },
                body: JSON.stringify({ user_ids: selections[roleToSubmit] })
            });
            if (!response.ok) throw new Error('Assignment failed.');
            
            setSelections({ developers: [], testers: [], managers: [] });
            await fetchData();
        } catch (err) {
            setError(err.message || 'Failed to assign members.');
            console.error(err);
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
            <div 
                className="rounded-2xl shadow-2xl w-full max-w-xl m-4" // Adjusted width for single column
                style={{ background: "linear-gradient(135deg, rgba(173, 151, 253, 0.95) 0%, rgba(246, 165, 220, 0.95) 100%)" }}
                onClick={e => e.stopPropagation()}
            >
                <div className="p-5 border-b border-white/30">
                    <h2 className="text-2xl font-bold text-gray-900">Manage Team: {project.name}</h2>
                </div>
                <div className="p-6 min-h-[400px]">
                    {loading ? <div className="flex justify-center items-center h-full"><Loader2 className="animate-spin h-12 w-12 text-indigo-700" /></div> : (
                        <>
                            <div className="mb-6">
                                <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center"><ShieldCheck className="text-green-800 mr-2" /> Current Team</h3>
                                <div className="flex flex-wrap gap-2 p-2 bg-white/30 rounded-md min-h-[40px]">
                                    {assignedMembers.length > 0 ? assignedMembers.map(m => <span key={m.user.id} className="bg-white/70 text-gray-800 text-sm px-3 py-1 rounded-full">{m.user.first_name} ({m.role})</span>) : <span className="text-gray-700 p-1">No members assigned.</span>}
                                </div>
                            </div>

                            {/* --- UPDATED: Replaced three lists with one dropdown --- */}
                            <div className="flex flex-col gap-6">
                                <UnifiedSearchableDropdown
                                    allMembers={allAvailableMembers}
                                    selections={selections}
                                    onSelect={handleSelect}
                                />
                            </div>

                            {showWarning && (
                                <div className="mt-4 p-3 bg-amber-100 border border-amber-400 text-amber-800 rounded-md flex items-start gap-3">
                                    <AlertTriangle />
                                    <p className="text-sm">You can only assign from one role at a time. Your selections for the other role(s) have been cleared.</p>
                                </div>
                            )}
                             {error && <p className="text-red-800 font-semibold text-sm mt-4 text-center">{error}</p>}
                        </>
                    )}
                </div>
                <div className="flex justify-end gap-4 p-4 bg-white/20 border-t border-white/30">
                    <button onClick={onClose} className="px-4 py-2 bg-white/50 hover:bg-white/80 text-gray-800 rounded-md">Close</button>
                    <button onClick={handleSubmit} disabled={submitting || loading || Object.values(selections).every(arr => arr.length === 0)} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md disabled:bg-indigo-400 disabled:cursor-not-allowed flex items-center">
                        {submitting && <Loader2 className="animate-spin mr-2" />}
                        Assign
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ManageTeamModal;

