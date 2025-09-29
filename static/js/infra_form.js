let currentStep = 1;

function showStep(step) {
    console.log(`Showing step ${step}`);
    document.querySelectorAll('.step').forEach(s => {
        s.style.display = 'none';
    });
    const currentStepElement = document.getElementById(`step${step}`);
    if (currentStepElement) {
        currentStepElement.style.display = 'block';
    }
    currentStep = step;
    
    // Update step indicators if you have them
    updateStepIndicator();
}

function updateStepIndicator() {
    // Remove active class from all indicators
    document.querySelectorAll('.step-indicator').forEach(indicator => {
        indicator.classList.remove('active');
    });
    
    // Add active class to current step
    const currentIndicator = document.querySelector(`.step-indicator[data-step="${currentStep}"]`);
    if (currentIndicator) {
        currentIndicator.classList.add('active');
    }
}

function nextStep(current) {
    console.log(`Next step from ${current} to ${current + 1}`);
    if (validateStep(current)) {
        showStep(current + 1);
        
        // Load data for the next step
        if (current + 1 === 2) {
            loadVPCs();
        } else if (current + 1 === 3) {
            loadSecurityGroupsForAllTypes();
        } else if (current + 1 === 4) {
            loadKeyPairs();
        }
    }
}

function prevStep(current) {
    console.log(`Previous step from ${current} to ${current - 1}`);
    if (current > 1) {
        showStep(current - 1);
    }
}

function validateStep(step) {
    console.log(`Validating step ${step}`);
    switch(step) {
        case 1:
            const infraName = document.getElementById('infra_name').value.trim();
            if (!infraName) {
                alert('Please enter an infrastructure name');
                return false;
            }
            // Validate infra name format (alphanumeric and hyphens only)
            if (!/^[a-zA-Z0-9-]+$/.test(infraName)) {
                alert('Infrastructure name can only contain letters, numbers, and hyphens');
                return false;
            }
            return true;
            
        case 2:
            const createNewVpc = document.getElementById('create_new_vpc').checked;
            if (createNewVpc) {
                const vpcName = document.getElementById('vpc_name').value.trim();
                if (!vpcName) {
                    alert('Please enter a VPC name');
                    return false;
                }
            } else {
                const existingVpc = document.getElementById('existing_vpc').value;
                if (!existingVpc) {
                    alert('Please select a VPC');
                    return false;
                }
            }
            return true;
            
        case 3:
            // Check if at least one security group is selected
            const sgCheckboxes = document.querySelectorAll('input[name="sg_types"]:checked');
            if (sgCheckboxes.length === 0) {
                alert('Please select at least one security group type');
                return false;
            }
            
            // Validate that if security groups are selected, their options are properly configured
            const sgTypes = ['alb', 'server', 'rds', 'vpn'];
            for (const sgType of sgTypes) {
                const checkbox = document.getElementById(`${sgType}_sg`);
                if (checkbox && checkbox.checked) {
                    const existingRadio = document.getElementById(`${sgType}_sg_existing`);
                    if (existingRadio && existingRadio.checked) {
                        const existingSelect = document.getElementById(`existing_sg_${sgType}`);
                        if (!existingSelect || !existingSelect.value) {
                            alert(`Please select an existing security group for ${sgType} or choose to create a new one`);
                            return false;
                        }
                    }
                }
            }
            return true;
            
        case 4:
            const instanceType = document.getElementById('instance_type').value;
            if (!instanceType) {
                alert('Please select an instance type');
                return false;
            }
            
            const keyPairOption = document.querySelector('input[name="key_pair_option"]:checked');
            if (!keyPairOption) {
                alert('Please select a key pair option');
                return false;
            }
            
            if (keyPairOption.value === 'existing') {
                const existingKeyPair = document.getElementById('existing_key_pair').value;
                if (!existingKeyPair) {
                    alert('Please select an existing key pair');
                    return false;
                }
            } else if (keyPairOption.value === 'new') {
                const newKeyName = document.getElementById('new_key_name').value.trim();
                if (!newKeyName) {
                    alert('Please enter a name for the new key pair');
                    return false;
                }
                // Validate key name format
                if (!/^[a-zA-Z0-9-]+$/.test(newKeyName)) {
                    alert('Key pair name can only contain letters, numbers, and hyphens');
                    return false;
                }
            }
            return true;
            
        default:
            return true;
    }
}

function toggleVpcOptions() {
    const createNewVpc = document.getElementById('create_new_vpc').checked;
    const newVpcSection = document.getElementById('new_vpc_section');
    const existingVpcSection = document.getElementById('existing_vpc_section');
    
    if (newVpcSection) newVpcSection.style.display = createNewVpc ? 'block' : 'none';
    if (existingVpcSection) existingVpcSection.style.display = createNewVpc ? 'none' : 'block';
    
    if (!createNewVpc) {
        loadVPCs();
    }
}

function loadVPCs() {
    const region = document.getElementById('region').value;
    const vpcSelect = document.getElementById('existing_vpc');
    
    if (!vpcSelect) {
        console.error('VPC select element not found');
        return;
    }
    
    vpcSelect.innerHTML = '<option value="">Loading VPCs...</option>';
    vpcSelect.disabled = true;
    
    fetch(`/get_vpcs?region=${region}`)
        .then(response => {
            console.log('VPC response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('VPCs data received:', data);
            
            vpcSelect.innerHTML = '<option value="">Select a VPC</option>';
            
            if (data.error) {
                vpcSelect.innerHTML = `<option value="">Error: ${data.error}</option>`;
                return;
            }
            
            if (!Array.isArray(data)) {
                vpcSelect.innerHTML = '<option value="">Invalid response format</option>';
                return;
            }
            
            if (data.length === 0) {
                vpcSelect.innerHTML = '<option value="">No VPCs found in this region</option>';
                return;
            }
            
            data.forEach(vpc => {
                const option = document.createElement('option');
                option.value = vpc.VpcId;
                const vpcName = vpc.Name || 'Unnamed';
                option.textContent = `${vpcName} (${vpc.VpcId}) - ${vpc.CidrBlock}`;
                vpcSelect.appendChild(option);
            });
            
            vpcSelect.disabled = false;
        })
        .catch(error => {
            console.error('Error loading VPCs:', error);
            vpcSelect.innerHTML = `<option value="">Error: ${error.message}</option>`;
            vpcSelect.disabled = false;
        });
}

function toggleSgOptions(sgType) {
    const checkbox = document.getElementById(`${sgType}_sg`);
    const section = document.getElementById(`${sgType}_sg_section`);
    if (section && checkbox) {
        section.style.display = checkbox.checked ? 'block' : 'none';
        
        // If unchecking, reset the options
        if (!checkbox.checked) {
            const newRadio = document.getElementById(`${sgType}_sg_new`);
            if (newRadio) newRadio.checked = true;
            const existingSection = document.getElementById(`${sgType}_sg_existing_section`);
            if (existingSection) existingSection.style.display = 'none';
        }
    }
}

function toggleSgType(sgType, optionType) {
    const existingSection = document.getElementById(`${sgType}_sg_existing_section`);
    if (existingSection) {
        if (optionType === 'existing') {
            existingSection.style.display = 'block';
            loadSecurityGroupsForType(sgType);
        } else {
            existingSection.style.display = 'none';
        }
    }
}

function loadSecurityGroupsForType(sgType) {
    const region = document.getElementById('region').value;
    const vpcId = document.getElementById('existing_vpc').value;
    const select = document.getElementById(`existing_sg_${sgType}`);
    
    if (!select) {
        console.error(`Security group select for ${sgType} not found`);
        return;
    }
    
    if (!vpcId || vpcId === '') {
        select.innerHTML = '<option value="">Please select a VPC first</option>';
        select.disabled = true;
        return;
    }
    
    select.innerHTML = '<option value="">Loading security groups...</option>';
    select.disabled = true;
    
    fetch(`/get_security_groups?region=${region}&vpc_id=${vpcId}`)
        .then(response => {
            console.log(`Security groups response for ${sgType}:`, response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log(`Security groups for ${sgType}:`, data);
            
            select.innerHTML = '<option value="">Select a security group</option>';
            
            if (data.error) {
                select.innerHTML = `<option value="">Error: ${data.error}</option>`;
                return;
            }
            
            if (!Array.isArray(data)) {
                select.innerHTML = '<option value="">Invalid response format</option>';
                return;
            }
            
            if (data.length === 0) {
                select.innerHTML = '<option value="">No security groups found</option>';
                return;
            }
            
            data.forEach(sg => {
                const option = document.createElement('option');
                option.value = sg.GroupId;
                const description = sg.Description ? sg.Description.substring(0, 50) + '...' : 'No description';
                option.textContent = `${sg.GroupName} (${sg.GroupId}) - ${description}`;
                select.appendChild(option);
            });
            
            select.disabled = false;
        })
        .catch(error => {
            console.error(`Error loading security groups for ${sgType}:`, error);
            select.innerHTML = `<option value="">Error: ${error.message}</option>`;
            select.disabled = false;
        });
}

function loadSecurityGroupsForAllTypes() {
    const sgTypes = ['alb', 'server', 'rds', 'vpn'];
    sgTypes.forEach(sgType => {
        const checkbox = document.getElementById(`${sgType}_sg`);
        if (checkbox && checkbox.checked) {
            const existingRadio = document.getElementById(`${sgType}_sg_existing`);
            if (existingRadio && existingRadio.checked) {
                loadSecurityGroupsForType(sgType);
            }
        }
    });
}

function toggleKeyPairOptions() {
    const useExisting = document.getElementById('key_pair_existing').checked;
    document.getElementById('existing_key_section').style.display = useExisting ? 'block' : 'none';
    document.getElementById('new_key_section').style.display = useExisting ? 'none' : 'block';
}

function loadKeyPairs() {
    const region = document.getElementById('region').value;
    const keyPairSelect = document.getElementById('existing_key_pair');
    
    if (!keyPairSelect) {
        console.error('Key pair select element not found');
        return;
    }
    
    keyPairSelect.innerHTML = '<option value="">Loading key pairs...</option>';
    keyPairSelect.disabled = true;
    
    fetch(`/api/key-pairs?region=${region}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Key pairs data received:', data);
            
            keyPairSelect.innerHTML = '<option value="">Select key pair...</option>';
            
            if (data.error) {
                keyPairSelect.innerHTML = `<option value="">Error: ${data.error}</option>`;
                return;
            }
            
            if (data.key_pairs && data.key_pairs.length > 0) {
                data.key_pairs.forEach(key => {
                    const option = document.createElement('option');
                    option.value = key.KeyName;
                    option.textContent = key.KeyName;
                    keyPairSelect.appendChild(option);
                });
            } else {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'No key pairs found';
                keyPairSelect.appendChild(option);
            }
            
            keyPairSelect.disabled = false;
        })
        .catch(error => {
            console.error('Error loading key pairs:', error);
            keyPairSelect.innerHTML = '<option value="">Error loading key pairs</option>';
            keyPairSelect.disabled = false;
        });
}

function createInfrastructure() {
    console.log('Creating infrastructure...');
    if (!validateStep(4)) return;
    
    // Collect all form data using FormData
    const formData = new FormData(document.getElementById('infraForm'));
    
    // Convert FormData to object
    const data = {
        infra_name: formData.get('infra_name'),
        region: formData.get('region'),
        create_new_vpc: formData.get('create_new_vpc') === 'on',
        vpc_name: formData.get('vpc_name') || '',
        public_subnets: parseInt(formData.get('public_subnets') || '2'),
        private_subnets: parseInt(formData.get('private_subnets') || '2'),
        existing_vpc: formData.get('existing_vpc') || '',
        
        // Security groups - this should include ALL checked security groups
        sg_types: formData.getAll('sg_types'),
        
        // Security group options
        alb_sg_option: formData.get('alb_sg_option') || 'new',
        server_sg_option: formData.get('server_sg_option') || 'new',
        rds_sg_option: formData.get('rds_sg_option') || 'new',
        vpn_sg_option: formData.get('vpn_sg_option') || 'new',
        
        // Existing security group IDs
        existing_sg_alb: formData.get('existing_sg_alb') || '',
        existing_sg_server: formData.get('existing_sg_server') || '',
        existing_sg_rds: formData.get('existing_sg_rds') || '',
        existing_sg_vpn: formData.get('existing_sg_vpn') || '',

        
        // EC2 Configuration
        instance_type: formData.get('instance_type'),
        key_pair_option: formData.get('key_pair_option'),
        existing_key_pair: formData.get('existing_key_pair') || '',
        new_key_name: formData.get('new_key_name') || ''
    };
    
    console.log('Form data to send:', data);
    
    // Show loading state
    const button = document.querySelector('button[onclick="createInfrastructure()"]');
    if (!button) {
        console.error('Create infrastructure button not found!');
        alert('Error: Create button not found. Please refresh the page.');
        return;
    }
    
    const originalText = button.innerHTML;
    button.innerHTML = '🔄 Creating...';
    button.disabled = true;
    
    // Disable all form elements during submission
    const formElements = document.getElementById('infraForm').elements;
    for (let i = 0; i < formElements.length; i++) {
        formElements[i].disabled = true;
    }
    
    fetch('/create_infra', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => {
        console.log('Response status:', response.status);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(result => {
        console.log('Create infra response:', result);
        if (result.success && result.operation_id) {
            console.log('Redirecting to status page...');
            window.location.href = `/infra_status/${result.operation_id}`;
        } else {
            const errorMessage = result.error || 'Unknown error occurred';
            console.error('Error from server:', errorMessage);
            alert('Error starting infrastructure creation: ' + errorMessage);
            resetFormState(button, originalText, formElements);
        }
    })
    .catch(error => {
        console.error('Error creating infrastructure:', error);
        alert('Error: ' + error.message);
        resetFormState(button, originalText, formElements);
    });
}

function resetFormState(button, originalText, formElements) {
    button.innerHTML = originalText;
    button.disabled = false;
    
    // Re-enable all form elements
    if (formElements) {
        for (let i = 0; i < formElements.length; i++) {
            formElements[i].disabled = false;
        }
    }
}

// Update instance type in review section
function updateInstanceTypeReview() {
    const instanceTypeSelect = document.getElementById('instance_type');
    const reviewElement = document.getElementById('review_instance_type');
    
    if (instanceTypeSelect && reviewElement) {
        instanceTypeSelect.addEventListener('change', function() {
            reviewElement.textContent = this.value;
        });
        
        // Set initial value
        reviewElement.textContent = instanceTypeSelect.value;
    }
}

// Initialize the form when page loads
document.addEventListener('DOMContentLoaded', function() {
    console.log('Page loaded, initializing form...');
    showStep(1); // Show first step
    
    // Load initial data
    loadVPCs();
    loadKeyPairs();
    
    // Initialize instance type review
    updateInstanceTypeReview();
    
    // Add event listeners for dynamic loading
    const regionSelect = document.getElementById('region');
    if (regionSelect) {
        regionSelect.addEventListener('change', function() {
            console.log('Region changed to:', this.value);
            loadVPCs();
            loadKeyPairs();
            loadSecurityGroupsForAllTypes();
        });
    }
    
    const vpcSelect = document.getElementById('existing_vpc');
    if (vpcSelect) {
        vpcSelect.addEventListener('change', function() {
            console.log('VPC changed to:', this.value);
            loadSecurityGroupsForAllTypes();
        });
    }
    
    // Initialize security group sections
    const sgTypes = ['alb', 'server', 'rds', 'vpn'];
    sgTypes.forEach(sgType => {
        const checkbox = document.getElementById(`${sgType}_sg`);
        if (checkbox) {
            // Set initial state
            toggleSgOptions(sgType);
            
            // Add change listener
            checkbox.addEventListener('change', function() {
                toggleSgOptions(sgType);
            });
        }
        
        // Add listeners for radio buttons
        const newRadio = document.getElementById(`${sgType}_sg_new`);
        const existingRadio = document.getElementById(`${sgType}_sg_existing`);
        
        if (newRadio) {
            newRadio.addEventListener('change', function() {
                toggleSgType(sgType, 'new');
            });
        }
        
        if (existingRadio) {
            existingRadio.addEventListener('change', function() {
                toggleSgType(sgType, 'existing');
            });
        }
    });
    
    // Initialize key pair options
    const keyPairExisting = document.getElementById('key_pair_existing');
    const keyPairNew = document.getElementById('key_pair_new');
    
    if (keyPairExisting && keyPairNew) {
        keyPairExisting.addEventListener('change', toggleKeyPairOptions);
        keyPairNew.addEventListener('change', toggleKeyPairOptions);
        toggleKeyPairOptions(); // Set initial state
    }
    
    console.log('Form initialization complete');
});