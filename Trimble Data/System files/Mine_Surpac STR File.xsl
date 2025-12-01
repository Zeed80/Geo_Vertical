<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform" xmlns:fo="http://www.w3.org/1999/XSL/Format">

<xsl:output method="text" omit-xml-declaration="yes" encoding="ISO-8859-1"/>
<xsl:variable name="fileExt" select="'str'"/>


<xsl:template match="/">
	 
	 
	<xsl:value-of select="concat(JOBFile/@jobName,',',JOBFile/@TimeStamp,',,','Trimble TSC2')"/>
	<xsl:text>&#xa;</xsl:text>
	<xsl:text> 0,    0.000,   0.000,    0.000,    0.000,    0.000,   0.000</xsl:text>
	<xsl:text>&#xa;</xsl:text>
	
	<!--
	<xsl:value-of select="JOBFile/@version"/>
	<xsl:text>&#xa;</xsl:text>
	<xsl:value-of select="JOBFile/@TimeStamp"/>
	<xsl:text>&#xa;</xsl:text>
	-->
	
	<xsl:for-each select="JOBFile/Reductions/Point">

		
    <!-- When we are not on the first point check the code of first -->
    <!-- preceding point and if not the same output a 'zero' line   -->
    <xsl:if test="(position() != 1) and (preceding-sibling::Point[1]/Code != Code)">
      <xsl:text> 0, 0.000, 0.000, 0.000,</xsl:text>
      <xsl:text>&#xa;</xsl:text>
    </xsl:if>


		<xsl:text> 1 ,</xsl:text>
		
		<xsl:variable name="Code" select="Code"/>
		<xsl:variable name="Name" select="Name"/>
		<xsl:variable name="North" select='format-number(Grid/North,"#######.000")'/>
		<xsl:variable name="East" select='format-number(Grid/East,"######.000")'/>
		<xsl:variable name="Elevation" select='format-number(Grid/Elevation,"####.000")'/> 
		
		
		<xsl:value-of select='concat($North,",")'/>
		<xsl:value-of select='concat($East,",")'/>
		<xsl:value-of select='concat($Elevation,",")'/>
		<xsl:value-of select='concat($Name,",")'/>
		<xsl:value-of select="Code"/>
		<xsl:text>&#xa;</xsl:text>
		
	
		
		</xsl:for-each>
		
			
		<xsl:text> 0, 0.000, 0.000, 0.000,
 0, 0.000, 0.000, 0.000, END
		</xsl:text>
	
</xsl:template>
</xsl:stylesheet>
