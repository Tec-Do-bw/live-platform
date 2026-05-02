// 创建导航栏元素
function createNavBar() {
    // 创建导航栏容器
    const navBar = document.createElement('div');
    navBar.className = 'nav-bar';
    navBar.style.backgroundColor = '#007bff';
    navBar.style.color = 'white';
    navBar.style.padding = '10px 20px';
    navBar.style.display = 'flex';
    navBar.style.justifyContent = 'space-between';
    navBar.style.alignItems = 'center';
    navBar.style.boxShadow = '0 2px 5px rgba(0,0,0,0.1)';
    navBar.style.marginBottom = '20px';
    navBar.style.position = 'sticky';
    navBar.style.top = '0';
    navBar.style.zIndex = '1000';
    
    // 创建左侧标题
    const title = document.createElement('div');
    title.className = 'nav-title';
    title.textContent = 'liveLab-接口测试';
    title.style.fontSize = '1.5rem';
    title.style.fontWeight = 'bold';
    
    // 创建导航链接容器
    const navLinks = document.createElement('div');
    navLinks.className = 'nav-links';
    navLinks.style.display = 'flex';
    navLinks.style.gap = '20px';
    
    // 定义导航链接
    const links = [
        { text: '数据在线API', url: '/docs/doc', id: 'doc-link', requireAuth: false },
        { text: '数据接口管理', url: '/docs/configGenerator', id: 'config-link', requireAuth: true },
        { text: '离线任务管理', url: '/docs/offlineTask', id: 'task-link', requireAuth: true },
        { text: '数据需求池', url: '/docs/dataNeedForm', id: 'dataneed-link', requireAuth: false },
        { text: '更新说明', url: '/docs/versionHistory', id: 'version-link', requireAuth: false }
    ];
    
    // 添加链接到导航栏（先只添加不需要登录的链接）
    links.filter(link => !link.requireAuth).forEach(link => {
        const a = document.createElement('a');
        a.href = link.url;
        a.textContent = link.text;
        a.id = link.id;
        a.style.color = 'white';
        a.style.textDecoration = 'none';
        a.style.padding = '5px 10px';
        a.style.borderRadius = '4px';
        a.style.transition = 'background-color 0.3s';
        
        // 高亮当前页面
        if (window.location.pathname.includes(link.url)) {
            a.style.backgroundColor = 'rgba(255, 255, 255, 0.2)';
            a.style.fontWeight = 'bold';
        }
        
        a.onmouseover = function() {
            this.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
        };
        
        a.onmouseout = function() {
            if (!window.location.pathname.includes(link.url)) {
                this.style.backgroundColor = 'transparent';
            } else {
                this.style.backgroundColor = 'rgba(255, 255, 255, 0.2)';
            }
        };
        
        navLinks.appendChild(a);
    });
    
    // 创建用户信息容器
    const userInfo = document.createElement('div');
    userInfo.className = 'user-info';
    userInfo.style.display = 'flex';
    userInfo.style.alignItems = 'center';
    userInfo.style.gap = '15px';
    
    // 创建用户名显示元素
    const usernameElement = document.createElement('span');
    usernameElement.id = 'username-display';
    usernameElement.style.color = 'white';
    usernameElement.style.cursor = 'pointer'; // 添加指针样式表明可点击
    
    // 创建登出按钮
    const logoutButton = document.createElement('a');
    logoutButton.href = '/docs/logout';
    logoutButton.textContent = '登出';
    logoutButton.style.color = 'white';
    logoutButton.style.textDecoration = 'none';
    logoutButton.style.padding = '5px 10px';
    logoutButton.style.backgroundColor = 'rgba(220, 53, 69, 0.8)';
    logoutButton.style.borderRadius = '4px';
    logoutButton.style.display = 'none';
    logoutButton.id = 'logout-link';
    
    // 将元素添加到用户信息容器
    userInfo.appendChild(usernameElement);
    userInfo.appendChild(logoutButton);
    
    // 将所有元素添加到导航栏
    navBar.appendChild(title);
    navBar.appendChild(navLinks);
    navBar.appendChild(userInfo);
    
    // 将导航栏插入到body的第一个元素之前
    document.body.insertBefore(navBar, document.body.firstChild);
    
    // 如果是登录页面，不显示导航栏
    if (window.location.pathname.includes('/docs/login')) {
        navBar.style.display = 'none';
    }
    
    // 保存对navLinks的引用，以便在用户状态变化时更新
    window.navLinksContainer = navLinks;
    window.navLinksConfig = links;
}

// 检查当前页面是否需要登录验证
function isRestrictedPage() {
    const path = window.location.pathname;
    const restrictedPages = [
        '/docs/configGenerator',
        '/docs/offlineTask'
    ];
    
    return restrictedPages.some(page => path.includes(page));
}

// 获取并显示用户登录状态
function fetchUserStatus() {
    fetch('/docs/user_status')
        .then(response => response.json())
        .then(data => {
            const usernameElement = document.getElementById('username-display');
            const logoutButton = document.getElementById('logout-link');
            
            if (data.authenticated) {
                usernameElement.textContent = `${data.username}`;
                usernameElement.style.color = 'white';
                logoutButton.style.display = 'inline-block';
                // 已登录状态下移除点击事件
                usernameElement.onclick = null;
                usernameElement.style.cursor = 'default';
                
                // 添加需要登录的导航链接
                updateNavLinks(true);
            } else {
                usernameElement.textContent = '未登录';
                usernameElement.style.color = 'rgba(255, 255, 255, 0.7)';
                logoutButton.style.display = 'none';
                
                // 确保移除需要登录的导航链接
                updateNavLinks(false);
                
                // 添加点击事件，点击"未登录"文本跳转到登录页面
                usernameElement.onclick = function() {
                    // 保存当前页面URL以便登录后返回
                    const currentPath = encodeURIComponent(window.location.pathname);
                    window.location.href = `/docs/login?next=${currentPath}`;
                };
                
                // 添加鼠标悬停样式
                usernameElement.onmouseover = function() {
                    this.style.textDecoration = 'underline';
                };
                
                usernameElement.onmouseout = function() {
                    this.style.textDecoration = 'none';
                };
                
                // 如果是受限页面且用户未登录，则重定向到登录页面
                if (isRestrictedPage()) {
                    // 保存当前页面URL以便登录后返回
                    const currentPath = encodeURIComponent(window.location.pathname);
                    window.location.href = `/docs/login?next=${currentPath}`;
                }
            }
        })
        .catch(error => {
            console.error('获取用户状态失败:', error);
            document.getElementById('username-display').textContent = '未登录';
            updateNavLinks(false);
        });
}

// 更新导航链接，根据登录状态显示或隐藏需要权限的链接
function updateNavLinks(isAuthenticated) {
    if (!window.navLinksContainer || !window.navLinksConfig) return;
    
    const navLinks = window.navLinksContainer;
    const links = window.navLinksConfig;
    
    // 清空现有链接
    navLinks.innerHTML = '';
    
    // 添加链接到导航栏（根据登录状态筛选）
    links.filter(link => !link.requireAuth || isAuthenticated).forEach(link => {
        const a = document.createElement('a');
        a.href = link.url;
        a.textContent = link.text;
        a.id = link.id;
        a.style.color = 'white';
        a.style.textDecoration = 'none';
        a.style.padding = '5px 10px';
        a.style.borderRadius = '4px';
        a.style.transition = 'background-color 0.3s';
        
        // 高亮当前页面
        if (window.location.pathname.includes(link.url)) {
            a.style.backgroundColor = 'rgba(255, 255, 255, 0.2)';
            a.style.fontWeight = 'bold';
        }
        
        a.onmouseover = function() {
            this.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
        };
        
        a.onmouseout = function() {
            if (!window.location.pathname.includes(link.url)) {
                this.style.backgroundColor = 'transparent';
            } else {
                this.style.backgroundColor = 'rgba(255, 255, 255, 0.2)';
            }
        };
        
        navLinks.appendChild(a);
    });
}

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
    createNavBar();
    fetchUserStatus();
}); 